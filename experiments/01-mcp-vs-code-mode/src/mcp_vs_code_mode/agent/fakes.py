"""Simulated chat models for tests and the Phase 4 dry run.

SIMULATED: nothing here is a measurement. Token counts are rough character-based
estimates (``chars // 4``) and latency is a fixed tiny constant, and every response
carries ``simulated=True`` so downstream analysis can exclude it.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from mcp_vs_code_mode.agent.records import LLMResponse, LLMToolCall, Mode, Usage
from mcp_vs_code_mode.banking.dataset import WINDOW_END, WINDOW_START, customer_id_for
from mcp_vs_code_mode.scenarios.definitions import SCENARIO_A_ACCOUNT_ID, TaskSpec

SIMULATED_LATENCY_MS = 0.001


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def build_response(
    *,
    content: str | None,
    tool_calls: Sequence[LLMToolCall],
    prompt_tokens: int,
    completion_tokens: int | None = None,
) -> LLMResponse:
    """Assemble a simulated ``LLMResponse``."""
    if completion_tokens is None:
        output = content or "".join(tc.arguments for tc in tool_calls)
        completion_tokens = max(1, _estimate_tokens(output))
    assistant: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        assistant["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in tool_calls
        ]
    return LLMResponse(
        content=content,
        tool_calls=tuple(tool_calls),
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        latency_ms=SIMULATED_LATENCY_MS,
        attempts=1,
        client_wait_ms=0.0,
        provider="simulated",
        model="simulated",
        request_id=None,
        assistant_message=assistant,
        simulated=True,
    )


def scripted_tool_call(
    name: str, args: Mapping[str, Any], call_id: str, *, prompt_tokens: int = 100
) -> LLMResponse:
    """A response requesting one tool call."""
    call = LLMToolCall(id=call_id, name=name, arguments=json.dumps(dict(args)))
    return build_response(content=None, tool_calls=[call], prompt_tokens=prompt_tokens)


def scripted_text(text: str, *, prompt_tokens: int = 100) -> LLMResponse:
    """A final text response."""
    return build_response(content=text, tool_calls=[], prompt_tokens=prompt_tokens)


class ScriptedChatModel:
    """Returns (or raises) pre-defined items in order."""

    def __init__(self, responses: Sequence[LLMResponse | Exception]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> LLMResponse:
        """Return the next scripted item."""
        if self._index >= len(self._responses):
            raise AssertionError("ScriptedChatModel exhausted")
        item = self._responses[self._index]
        self._index += 1
        self.seen_messages.append([dict(m) for m in messages])
        if isinstance(item, Exception):
            raise item
        return item


_SCRIPT_A = """\
balance = get_balance("{account_id}")
{{
    "account_id": balance["account_id"],
    "available_balance": balance["available_balance"],
    "currency": balance["currency"],
}}
"""

_SCRIPT_B = """\
accounts = []
total = 0.0
for account in list_accounts("{customer_id}"):
    account_id = account["account_id"]
    available = get_balance(account_id)["available_balance"]
    spend = {{}}
    large = []
    for txn in get_transactions(account_id, "{start}", "{end}"):
        if txn["amount"] < 0:
            absolute = abs(txn["amount"])
            spend[txn["category"]] = spend.get(txn["category"], 0) + absolute
            if absolute > 1000:
                large.append(txn["transaction_id"])
    accounts.append({{
        "account_id": account_id,
        "available_balance": available,
        "spend_by_category": {{k: round(v, 2) for k, v in sorted(spend.items())}},
        "large_debit_ids": sorted(large),
    }})
    total += available
{{"customer_id": "{customer_id}", "accounts": accounts, "total_available_balance": round(total, 2)}}
"""


def _prompt_tokens(
    messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
) -> int:
    return _estimate_tokens(json.dumps(list(messages)) + json.dumps(list(tools)))


class OracleChatModel:
    """Deterministic "perfect agent". Reads tool results only from ``messages``."""

    def __init__(self, task: TaskSpec, mode: Mode) -> None:
        self._task = task
        self._mode = mode

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> LLMResponse:
        """Produce the next step of the reference solution."""
        turn = sum(1 for m in messages if m.get("role") == "assistant") + 1
        prompt_tokens = _prompt_tokens(messages, tools)
        if self._mode == "code":
            return self._code_step(turn, messages, prompt_tokens)
        return self._mcp_step(turn, messages, prompt_tokens)

    def _calls(
        self, specs: Sequence[tuple[str, Mapping[str, Any]]], turn: int, prompt_tokens: int
    ) -> LLMResponse:
        calls = [
            LLMToolCall(id=f"call_{turn}_{i}", name=name, arguments=json.dumps(dict(args)))
            for i, (name, args) in enumerate(specs)
        ]
        return build_response(content=None, tool_calls=calls, prompt_tokens=prompt_tokens)

    def _code_step(
        self, turn: int, messages: Sequence[Mapping[str, Any]], prompt_tokens: int
    ) -> LLMResponse:
        if turn == 1:
            if self._task.scenario == "A":
                code = _SCRIPT_A.format(account_id=SCENARIO_A_ACCOUNT_ID)
            else:
                assert self._task.volume is not None
                code = _SCRIPT_B.format(
                    customer_id=customer_id_for(self._task.volume),
                    start=WINDOW_START.isoformat(),
                    end=WINDOW_END.isoformat(),
                )
            return self._calls([("run_python", {"code": code})], turn, prompt_tokens)
        payload = json.loads(str(_tool_messages(messages)[-1]["content"]))
        text = json.dumps(payload["result"])
        return build_response(content=text, tool_calls=[], prompt_tokens=prompt_tokens)

    def _mcp_step(
        self, turn: int, messages: Sequence[Mapping[str, Any]], prompt_tokens: int
    ) -> LLMResponse:
        results = _results_by_call(messages)
        if self._task.scenario == "A":
            if turn == 1:
                return self._calls(
                    [("get_balance", {"account_id": SCENARIO_A_ACCOUNT_ID})], turn, prompt_tokens
                )
            balance = _only(results, "get_balance")
            answer = {
                "account_id": balance["account_id"],
                "available_balance": balance["available_balance"],
                "currency": balance["currency"],
            }
            return build_response(
                content=json.dumps(answer), tool_calls=[], prompt_tokens=prompt_tokens
            )
        assert self._task.volume is not None
        customer_id = customer_id_for(self._task.volume)
        if turn == 1:
            return self._calls(
                [("list_accounts", {"customer_id": customer_id})], turn, prompt_tokens
            )
        if turn == 2:
            accounts = _only(results, "list_accounts")
            specs: list[tuple[str, Mapping[str, Any]]] = []
            for account in accounts:
                account_id = account["account_id"]
                specs.append(("get_balance", {"account_id": account_id}))
                specs.append(
                    (
                        "get_transactions",
                        {
                            "account_id": account_id,
                            "start_date": WINDOW_START.isoformat(),
                            "end_date": WINDOW_END.isoformat(),
                        },
                    )
                )
            return self._calls(specs, turn, prompt_tokens)
        answer = _answer_b_from_results(customer_id, results)
        return build_response(
            content=json.dumps(answer), tool_calls=[], prompt_tokens=prompt_tokens
        )


def _tool_messages(messages: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [m for m in messages if m.get("role") == "tool"]


def _results_by_call(
    messages: Sequence[Mapping[str, Any]],
) -> list[tuple[str, dict[str, Any], Any]]:
    """(tool name, arguments, parsed result) for every tool call answered in ``messages``."""
    requested: dict[str, tuple[str, dict[str, Any]]] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call["function"]
            requested[call["id"]] = (function["name"], json.loads(function["arguments"]))
    out: list[tuple[str, dict[str, Any], Any]] = []
    for message in _tool_messages(messages):
        name, args = requested[message["tool_call_id"]]
        out.append((name, args, json.loads(message["content"])))
    return out


def _only(results: list[tuple[str, dict[str, Any], Any]], name: str) -> Any:
    for tool, _, value in results:
        if tool == name:
            return value
    raise AssertionError(f"No {name} result in messages")


def _answer_b_from_results(
    customer_id: str, results: list[tuple[str, dict[str, Any], Any]]
) -> dict[str, Any]:
    account_ids = sorted(a["account_id"] for a in _only(results, "list_accounts"))
    balances = {a["account_id"]: v for n, a, v in results if n == "get_balance"}
    transactions = {a["account_id"]: v for n, a, v in results if n == "get_transactions"}
    accounts: list[dict[str, Any]] = []
    total = 0.0
    for account_id in account_ids:
        available = balances[account_id]["available_balance"]
        spend: dict[str, float] = {}
        large: list[str] = []
        for txn in transactions[account_id]:
            if txn["amount"] >= 0:
                continue
            absolute = abs(txn["amount"])
            spend[txn["category"]] = spend.get(txn["category"], 0.0) + absolute
            if absolute > 1000:
                large.append(txn["transaction_id"])
        accounts.append(
            {
                "account_id": account_id,
                "available_balance": available,
                "spend_by_category": {k: round(v, 2) for k, v in sorted(spend.items())},
                "large_debit_ids": sorted(large),
            }
        )
        total += available
    return {
        "customer_id": customer_id,
        "accounts": accounts,
        "total_available_balance": round(total, 2),
    }
