"""Single source of truth for the four benchmark tools.

Both MCP mode and Code Mode derive their tool interface from ``TOOL_SPECS`` and
execute through ``ToolExecutor``. Timeouts are enforced at the transport layer
in Phase 3 (MCP call timeout, Monty limits), not here.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from mcp_vs_code_mode.banking.audit import Channel
from mcp_vs_code_mode.banking.auth import Principal
from mcp_vs_code_mode.banking.errors import (
    AuthorizationError,
    InvalidRequestError,
    NotFoundError,
)
from mcp_vs_code_mode.banking.service import BankingService
from mcp_vs_code_mode.tools.errors import (
    ToolAccessError,
    ToolInputError,
    ToolNotFoundError,
    UnknownToolError,
)

_CUSTOMER_ID_PATTERN = r"^CUST-\d{4}$"
_ACCOUNT_ID_PATTERN = r"^ACC-\d{4}-\d$"


class GetCustomerInput(BaseModel):
    """Arguments for ``get_customer``."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        pattern=_CUSTOMER_ID_PATTERN, description="Customer ID, e.g. CUST-0050"
    )


class ListAccountsInput(BaseModel):
    """Arguments for ``list_accounts``."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(
        pattern=_CUSTOMER_ID_PATTERN, description="Customer ID, e.g. CUST-0050"
    )


class GetBalanceInput(BaseModel):
    """Arguments for ``get_balance``."""

    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(pattern=_ACCOUNT_ID_PATTERN, description="Account ID, e.g. ACC-0050-1")


class GetTransactionsInput(BaseModel):
    """Arguments for ``get_transactions``."""

    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(pattern=_ACCOUNT_ID_PATTERN, description="Account ID, e.g. ACC-0050-1")
    start_date: date = Field(description="Inclusive start date, YYYY-MM-DD")
    end_date: date = Field(description="Inclusive end date, YYYY-MM-DD")

    @model_validator(mode="after")
    def _check_range(self) -> "GetTransactionsInput":
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


@dataclass(frozen=True)
class ToolSpec:
    """Tool definition. ``description`` is used verbatim by both modes."""

    name: str
    description: str
    input_model: type[BaseModel]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_customer",
        description="Get a customer's profile. Returns {customer_id, name, segment}.",
        input_model=GetCustomerInput,
    ),
    ToolSpec(
        name="list_accounts",
        description=(
            "List a customer's accounts. "
            "Returns a list of {account_id, customer_id, account_type, currency}."
        ),
        input_model=ListAccountsInput,
    ),
    ToolSpec(
        name="get_balance",
        description=(
            "Get an account's balance. "
            "Returns {account_id, available_balance, ledger_balance, currency, as_of}."
        ),
        input_model=GetBalanceInput,
    ),
    ToolSpec(
        name="get_transactions",
        description=(
            "List an account's transactions between two dates (inclusive). "
            "Returns a list of {transaction_id, account_id, date, amount, currency, merchant, "
            "category, description}. Negative amount = debit."
        ),
        input_model=GetTransactionsInput,
    ),
)

_ANY_ADAPTER: TypeAdapter[Any] = TypeAdapter(Any)


class ToolExecutor:
    """Executes allowlisted tools for one principal on one channel."""

    def __init__(self, service: BankingService, principal: Principal, channel: Channel) -> None:
        self._service = service
        self._principal = principal
        self._channel: Channel = channel
        self._specs_by_name = {spec.name: spec for spec in TOOL_SPECS}

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """The allowlisted tool specs."""
        return TOOL_SPECS

    def execute(self, name: str, arguments: Mapping[str, Any]) -> JsonValue:
        """Validate and run a tool, returning JSON-compatible data."""
        spec = self._specs_by_name.get(name)
        if spec is None:
            raise UnknownToolError(f"Unknown tool: {name}")
        try:
            parsed = spec.input_model.model_validate(dict(arguments))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}"
                for err in exc.errors(include_input=False, include_url=False)
            )
            raise ToolInputError(details) from exc
        try:
            result = self._dispatch(name, parsed)
        except AuthorizationError as exc:
            raise ToolAccessError("Access denied") from exc
        except NotFoundError as exc:
            raise ToolNotFoundError(str(exc)) from exc
        except InvalidRequestError as exc:
            raise ToolInputError(str(exc)) from exc
        dumped: JsonValue = _ANY_ADAPTER.dump_python(result, mode="json")
        return dumped

    def _dispatch(self, name: str, parsed: BaseModel) -> object:
        principal, channel = self._principal, self._channel
        match name:
            case "get_customer":
                assert isinstance(parsed, GetCustomerInput)
                return self._service.get_customer(principal, parsed.customer_id, channel=channel)
            case "list_accounts":
                assert isinstance(parsed, ListAccountsInput)
                return self._service.list_accounts(principal, parsed.customer_id, channel=channel)
            case "get_balance":
                assert isinstance(parsed, GetBalanceInput)
                return self._service.get_balance(principal, parsed.account_id, channel=channel)
            case "get_transactions":
                assert isinstance(parsed, GetTransactionsInput)
                return self._service.get_transactions(
                    principal,
                    parsed.account_id,
                    parsed.start_date,
                    parsed.end_date,
                    channel=channel,
                )
            case _:  # pragma: no cover - guarded by the allowlist check in execute()
                raise UnknownToolError(f"Unknown tool: {name}")
