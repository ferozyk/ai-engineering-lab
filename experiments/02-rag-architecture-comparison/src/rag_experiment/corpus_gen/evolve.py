"""The state of one product at one version, and the recorded steps from one version to the next.

A step applies two to four *systematic* differences chosen by a seeded generator, so the same
corpus is produced on every run. Each difference is returned as a :class:`Change`; ``build.py``
turns them into ``CHANGES.json`` after the newer spec has been rendered (the JSON Pointer of a
change can only be known then).
"""

import random
from dataclasses import dataclass, replace

from rag_experiment.corpus_gen.vocab import Field, Product

SEED = 20261123

OP_ORDER = ("list", "get", "action", "create", "update", "close", "search")
OP_STATUSES: dict[str, tuple[int, ...]] = {
    "list": (200, 400, 401, 403, 429),
    "get": (200, 401, 403, 404),
    "create": (201, 400, 401, 403, 409, 422, 429),
    "update": (200, 400, 401, 403, 404, 409, 422),
    "close": (200, 401, 403, 404, 409),
    "action": (200, 400, 401, 403, 404, 409, 422, 429),
    "search": (200, 400, 401, 403),
}
PRODUCT_STATUSES = (400, 403, 404, 409, 422)  # statuses whose responses carry product codes
WRITE_OPS = ("action", "create", "update")  # operations that take an Idempotency-Key header

KINDS = (
    "field_renamed",
    "page_size_max_changed",
    "amount_max_changed",
    "param_required",
    "operation_added",
    "operation_deprecated",
    "error_meaning_changed",
    "error_status_changed",
    "scope_renamed",
    "scope_split",
)

_MEANING_SUFFIX = {
    400: "and the error is reported before any other check",
    403: "and the refusal is recorded in the audit log",
    404: "and no details about the {resource} are returned",
    409: "and the change was made by the issuer",
    422: "when pending items are counted as well",
}


@dataclass(frozen=True)
class ErrorCode:
    """One ``ERR-<PREFIX>-<NNN>`` code: HTTP status, meaning and the operation that lists it."""

    code: str
    status: int
    clause: str  # "the card is frozen"
    op: str  # operation key the code is attached to


@dataclass(frozen=True)
class State:
    """Everything that can differ between versions of one product."""

    product: Product
    version: int
    ops: tuple[str, ...]
    fields: tuple[Field, ...]
    page_max: int
    idem_required: frozenset[str]
    deprecated: frozenset[str]
    errors: tuple[ErrorCode, ...]
    scopes: tuple[tuple[str, str], ...]  # scope name -> description, in order
    roles: tuple[tuple[str, str], ...]  # role (read/write/admin) -> scope name
    changed_codes: frozenset[str] = frozenset()
    scope_renamed: bool = False
    scope_split: bool = False

    def role_scope(self, role: str) -> str:
        """The scope an operation of this role requires."""
        return dict(self.roles)[role]

    def money_field(self) -> Field | None:
        """The first field with a maximum amount, if the product has one."""
        return next((f for f in self.fields if f.kind.startswith("money:")), None)


@dataclass(frozen=True)
class Change:
    """One recorded difference between two versions."""

    kind: str
    probe: tuple[str, ...]  # how ``render.locate`` finds it in the newer spec
    before: str | int | bool | None
    after: str | int | bool | None
    subject: str  # what changed: a field, parameter, operationId, error code or scope name


def ops_with_status(ops: tuple[str, ...], status: int) -> list[str]:
    """Operations (in order) that declare a response with this status."""
    return [o for o in ops if status in OP_STATUSES[o]]


def _pascal(text: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in text.split())


def operation_id(product: Product, op: str) -> str:
    """The operationId of an operation key."""
    if op == "action":
        return product.action.operation_id
    if op == "list":
        return f"list{_pascal(product.plural)}"
    if op == "search":
        return f"search{_pascal(product.plural)}"
    return f"{op}{product.type_name}"


def _initial_errors(product: Product, ops: tuple[str, ...]) -> tuple[ErrorCode, ...]:
    res = product.resource
    clauses: list[tuple[int, str]] = [
        (400, f"the {res} request is missing a required field"),
        (400, f"the {res} request has a field of the wrong type"),
        (403, f"the customer is not allowed to use this {res}"),
        (403, f"the application is not allowed to use this {res}"),
        (404, f"no {res} exists with that identifier"),
        (404, f"the {res} belongs to a different customer"),
    ]
    clauses += [(409, f"the {res} is {s.replace('_', ' ')}") for s in product.states]
    clauses += [
        (422, f"the {product.limit_noun} is above the {k} limit") for k in product.limit_kinds
    ]
    seen: dict[int, int] = {}
    errors: list[ErrorCode] = []
    for number, (status, clause) in enumerate(clauses, start=1):
        candidates = ops_with_status(ops, status)
        slot = seen.get(status, 0)
        seen[status] = slot + 1
        errors.append(
            ErrorCode(
                code=f"ERR-{product.prefix}-{number:03d}",
                status=status,
                clause=clause,
                op=candidates[slot % len(candidates)],
            )
        )
    return tuple(errors)


def initial_state(product: Product, index: int) -> State:
    """Version 1 of a product. ``index`` (its position in the table) sets the operation count."""
    count = 3 + index % 3
    ops = OP_ORDER[:count]
    if (
        count == 5 and index % 2 == 1
    ):  # alternate between "update" and "close" as the fifth operation
        ops = (*OP_ORDER[:4], "close")
    scope_read = f"{product.key}:read"
    scope_write = f"{product.key}:write"
    return State(
        product=product,
        version=1,
        ops=ops,
        fields=product.fields,
        page_max=(50, 50, 25, 100)[index % 4],
        idem_required=frozenset(),
        deprecated=frozenset(),
        errors=_initial_errors(product, ops),
        scopes=(
            (scope_read, f"Read {product.plural} and their current state."),
            (scope_write, f"Create, change and close {product.plural}."),
        ),
        roles=(("read", scope_read), ("write", scope_write), ("admin", scope_write)),
    )


# --------------------------------------------------------------------------- applicability


def _renamable(state: State) -> tuple[str, str] | None:
    names = {f.name for f in state.fields}
    return next((p for p in state.product.renames if p[0] in names and p[1] not in names), None)


def _next_idempotent(state: State) -> str | None:
    return next((o for o in WRITE_OPS if o in state.ops and o not in state.idem_required), None)


def _unchanged_errors(state: State) -> list[ErrorCode]:
    return [e for e in state.errors if e.code not in state.changed_codes]


def applicable(state: State, step: int) -> list[str]:
    """The change kinds that can still be applied to this state, in canonical order."""
    kinds = ["page_size_max_changed"]
    if _renamable(state):
        kinds.append("field_renamed")
    if state.money_field() is not None:
        kinds.append("amount_max_changed")
    if _next_idempotent(state):
        kinds.append("param_required")
    if step == 1 and "search" not in state.ops:
        kinds.append("operation_added")
    if "search" in state.ops and "list" not in state.deprecated:
        kinds.append("operation_deprecated")
    if _unchanged_errors(state):
        kinds.append("error_meaning_changed")
    if any(e.status in (409, 422) for e in _unchanged_errors(state)):
        kinds.append("error_status_changed")
    if not state.scope_renamed:
        kinds.append("scope_renamed")
    if not state.scope_split:
        kinds.append("scope_split")
    return [k for k in KINDS if k in kinds]


# --------------------------------------------------------------------------- applying one kind


def _replace_error(state: State, old: ErrorCode, new: ErrorCode) -> State:
    errors = tuple(new if e.code == old.code else e for e in state.errors)
    return replace(state, errors=errors, changed_codes=state.changed_codes | {old.code})


def _rename_field(state: State) -> tuple[State, Change]:
    pair = _renamable(state)
    assert pair is not None
    old_name, new_name = pair
    fields = tuple(replace(f, name=new_name) if f.name == old_name else f for f in state.fields)
    change = Change("field_renamed", ("schema_property", new_name), old_name, new_name, new_name)
    return replace(state, fields=fields), change


def _change_page_size(state: State) -> tuple[State, Change]:
    after = state.page_max * 2
    change = Change("page_size_max_changed", ("page_size",), state.page_max, after, "pageSize")
    return replace(state, page_max=after), change


def _change_amount_max(state: State) -> tuple[State, Change]:
    money = state.money_field()
    assert money is not None
    before = int(money.kind.split(":")[1])
    after = before * 2
    fields = tuple(
        replace(f, kind=f"money:{after}") if f.name == money.name else f for f in state.fields
    )
    change = Change("amount_max_changed", ("amount_max", money.name), before, after, money.name)
    return replace(state, fields=fields), change


def _require_idempotency(state: State) -> tuple[State, Change]:
    op = _next_idempotent(state)
    assert op is not None
    change = Change(
        "param_required", ("idempotency", op), "optional", "required", "Idempotency-Key"
    )
    return replace(state, idem_required=state.idem_required | {op}), change


def _add_search(state: State) -> tuple[State, Change]:
    search_id = operation_id(state.product, "search")
    change = Change("operation_added", ("operation", "search"), None, search_id, search_id)
    return replace(state, ops=(*state.ops, "search")), change


def _deprecate_list(state: State) -> tuple[State, Change]:
    replacement = operation_id(state.product, "search")
    change = Change(
        "operation_deprecated",
        ("deprecated", "list"),
        "not deprecated",
        f"deprecated, use {replacement}",
        operation_id(state.product, "list"),
    )
    return replace(state, deprecated=state.deprecated | {"list"}), change


def _change_error_meaning(state: State, rng: random.Random) -> tuple[State, Change]:
    pool = _unchanged_errors(state)
    old_error = pool[rng.randrange(len(pool))]
    suffix = _MEANING_SUFFIX[old_error.status].format(resource=state.product.resource)
    new_error = replace(old_error, clause=f"{old_error.clause} {suffix}")
    change = Change(
        "error_meaning_changed",
        ("error", old_error.code),
        old_error.clause,
        new_error.clause,
        old_error.code,
    )
    return _replace_error(state, old_error, new_error), change


def _change_error_status(state: State, rng: random.Random) -> tuple[State, Change]:
    pool = [e for e in _unchanged_errors(state) if e.status in (409, 422)]
    old_error = pool[rng.randrange(len(pool))]
    new_status = 422 if old_error.status == 409 else 409
    op = ops_with_status(state.ops, new_status)[0]
    new_error = replace(old_error, status=new_status, op=op)
    change = Change(
        "error_status_changed",
        ("error", old_error.code),
        old_error.status,
        new_status,
        old_error.code,
    )
    return _replace_error(state, old_error, new_error), change


def _rename_scope(state: State) -> tuple[State, Change]:
    old_name = state.role_scope("write")
    new_name = f"{state.product.key}:manage"
    scopes = tuple((new_name if n == old_name else n, d) for n, d in state.scopes)
    roles = tuple((r, new_name if n == old_name else n) for r, n in state.roles)
    change = Change("scope_renamed", ("scope", new_name), old_name, new_name, new_name)
    return replace(state, scopes=scopes, roles=roles, scope_renamed=True), change


def _split_scope(state: State) -> tuple[State, Change]:
    admin = f"{state.product.key}:admin"
    before = state.role_scope("admin")
    summary = state.product.action.summary
    text = f"Run privileged actions such as {summary[:1].lower()}{summary[1:]}."
    roles = tuple((r, admin if r == "admin" else n) for r, n in state.roles)
    change = Change("scope_split", ("scope", admin), before, admin, admin)
    return (
        replace(state, scopes=(*state.scopes, (admin, text)), roles=roles, scope_split=True),
        change,
    )


def _apply(state: State, kind: str, rng: random.Random) -> tuple[State, Change]:
    """Apply one kind of difference to a state and describe it."""
    plain = {
        "field_renamed": _rename_field,
        "page_size_max_changed": _change_page_size,
        "amount_max_changed": _change_amount_max,
        "param_required": _require_idempotency,
        "operation_added": _add_search,
        "operation_deprecated": _deprecate_list,
        "scope_renamed": _rename_scope,
        "scope_split": _split_scope,
    }
    if kind in plain:
        return plain[kind](state)
    if kind == "error_meaning_changed":
        return _change_error_meaning(state, rng)
    if kind == "error_status_changed":
        return _change_error_status(state, rng)
    raise ValueError(f"unknown change kind {kind}")


def evolve(state: State, has_v3: bool, rng_seed: str) -> tuple[State, list[Change]]:
    """The next version of a product and the 2-4 differences that were applied."""
    step = state.version  # 1 for v1 -> v2, 2 for v2 -> v3
    rng = random.Random(f"{SEED}:{rng_seed}:{step}")
    options = applicable(state, step)
    forced: list[str] = []
    if has_v3 and step == 1 and "operation_added" in options:
        forced.append("operation_added")
    if has_v3 and step == 2 and "operation_deprecated" in options:
        forced.append("operation_deprecated")
    count = max(2 + rng.randrange(3), len(forced))
    rest = [k for k in options if k not in forced]
    chosen = forced + rng.sample(rest, min(count - len(forced), len(rest)))
    changes: list[Change] = []
    current = replace(state, version=state.version + 1)
    for kind in [k for k in KINDS if k in chosen]:
        current, change = _apply(current, kind, rng)
        changes.append(change)
    return current, changes
