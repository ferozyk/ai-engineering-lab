"""Restricted Python execution for Code Mode, backed by a Monty subprocess pool."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal

from pydantic_monty import (
    Monty,
    MontyCrashedError,
    MontyError,
    MontyRuntimeError,
    MontySyntaxError,
    ResourceLimits,
)

from mcp_vs_code_mode.tools.errors import (
    ToolAccessError,
    ToolError,
    ToolInputError,
    ToolNotFoundError,
    UnknownToolError,
)
from mcp_vs_code_mode.tools.registry import TOOL_SPECS, ToolExecutor, ToolSpec


@dataclass(frozen=True)
class SandboxLimits:
    """Resource limits applied to every ``run`` call."""

    max_duration_secs: float = 5.0
    max_memory_bytes: int = 128 * 1024 * 1024
    max_host_calls: int = 100
    request_timeout_secs: float = 15.0


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of one sandbox run."""

    value: Any
    stdout: str
    error_type: str | None
    error_message: str | None
    host_calls: int
    duration_ms: float


class _CallCounter:
    def __init__(self) -> None:
        self.count = 0


def _make_host_function(
    spec: ToolSpec, executor: ToolExecutor, counter: _CallCounter
) -> Callable[..., Any]:
    field_names = list(spec.input_model.model_fields)

    def host_function(*args: Any, **kwargs: Any) -> Any:
        if len(args) > len(field_names):
            raise TypeError(
                f"{spec.name}() takes at most {len(field_names)} positional arguments "
                f"but {len(args)} were given"
            )
        merged: dict[str, Any] = dict(zip(field_names, args, strict=False))
        for key, value in kwargs.items():
            if key in merged:
                raise TypeError(f"{spec.name}() got multiple values for argument '{key}'")
            merged[key] = value
        counter.count += 1
        try:
            return executor.execute(spec.name, merged)
        except ToolAccessError as exc:
            raise PermissionError(str(exc)) from exc
        except ToolNotFoundError as exc:
            raise LookupError(str(exc)) from exc
        except ToolInputError as exc:
            raise ValueError(str(exc)) from exc
        except UnknownToolError as exc:
            raise NameError(str(exc)) from exc
        except ToolError as exc:  # pragma: no cover - defensive
            raise RuntimeError(str(exc)) from exc

    host_function.__name__ = spec.name
    return host_function


class CodeSandbox:
    """Runs model-written code in a Monty pool with only the allowlisted tools bound."""

    def __init__(self, executor: ToolExecutor, limits: SandboxLimits = SandboxLimits()) -> None:  # noqa: B008
        self._executor = executor
        self._limits = limits
        self._monty: Monty | None = None

    def __enter__(self) -> "CodeSandbox":
        self._monty = Monty(min_processes=1, request_timeout=self._limits.request_timeout_secs)
        self._monty.__enter__()
        self.warm_up()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._monty is not None:
            self._monty.__exit__(exc_type, exc, tb)
            self._monty = None

    def warm_up(self) -> float:
        """Run a trivial feed so the first measured run excludes worker start-up cost."""
        started = time.perf_counter()
        self._execute("1 + 1", _CallCounter(), [])
        return (time.perf_counter() - started) * 1000

    def run(self, code: str) -> SandboxResult:
        """Execute ``code`` in a fresh session and return value, output and any error."""
        counter = _CallCounter()
        chunks: list[str] = []
        started = time.perf_counter()
        error_type: str | None = None
        error_message: str | None = None
        value: Any = None
        try:
            value = self._execute(code, counter, chunks)
        except MontySyntaxError as exc:
            error_type, error_message = "syntax_error", exc.display(format="traceback")
        except MontyRuntimeError as exc:
            error_type, error_message = "runtime_error", exc.display(format="traceback")
        except MontyCrashedError as exc:
            error_type, error_message = "sandbox_crash", str(exc)
        except MontyError as exc:
            error_type, error_message = "sandbox_error", str(exc)
        return SandboxResult(
            value=value,
            stdout="".join(chunks),
            error_type=error_type,
            error_message=error_message,
            host_calls=counter.count,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    def _execute(self, code: str, counter: _CallCounter, chunks: list[str]) -> Any:
        if self._monty is None:
            raise RuntimeError("CodeSandbox must be used as a context manager")
        functions = {
            spec.name: _make_host_function(spec, self._executor, counter) for spec in TOOL_SPECS
        }

        def on_print(stream: Literal["stdout", "stderr"], text: str) -> None:
            chunks.append(text)

        limits = ResourceLimits(
            max_feed_duration_secs=self._limits.max_duration_secs,
            max_memory=self._limits.max_memory_bytes,
            max_suspensions=self._limits.max_host_calls,
        )
        with self._monty.checkout(limits=limits) as session:
            return session.feed_run(code, external_lookup=functions, print_callback=on_print)
