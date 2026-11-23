"""Render a product state as an OpenAPI 3.1 document, and find elements of a rendered document.

Only constructs that the chunker turns into chunks are used: operations, parameters, request
bodies, responses, security schemes and component schemas. Every sentence comes from a template.
"""

from collections.abc import Mapping
from typing import Any

from rag_experiment.corpus_gen.evolve import (
    OP_STATUSES,
    ErrorCode,
    State,
    operation_id,
)
from rag_experiment.corpus_gen.vocab import Field, Product
from rag_experiment.ingestion.pointers import pointer

DISCLAIMER = (
    "This is a synthetic specification for a fictional bank, written for a retrieval-augmented "
    "generation experiment. Nothing in it describes a real institution."
)
SERVER = "https://api.labbank.example"
TOKEN_URL = f"{SERVER}/oauth/token"
API_KEY_TEXT = (
    "Application key issued to the client when it was registered. It identifies the calling "
    "application and is sent with every request in addition to the bearer token."
)
ROLE_OF_OP = {
    "list": "read",
    "get": "read",
    "search": "read",
    "create": "write",
    "update": "write",
    "close": "admin",
    "action": "admin",
}
_LEADS = {
    400: "The request is malformed or fails validation.",
    403: "The caller is not allowed to perform this action.",
    404: "The {resource} was not found.",
    409: "The request conflicts with the current state of the {resource}.",
    422: "The request is well formed but breaks a business rule.",
}
Doc = dict[str, Any]


def _sentence(text: str) -> str:
    return text if text.endswith(".") else text + "."


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def document_id(product: Product, version: int) -> str:
    """The document id, and the file stem, of one version."""
    return f"{product.key}-api-v{version}"


def op_path(state: State, op: str) -> tuple[str, str]:
    """``(path, lower-case method)`` of an operation key."""
    p = state.product
    base = f"/v{state.version}/{p.segment}"
    member = f"{base}/{{{p.id_param}}}"
    return {
        "list": (base, "get"),
        "create": (base, "post"),
        "search": (f"{base}/search", "post"),
        "get": (member, "get"),
        "update": (member, "patch"),
        "close": (member, "delete"),
        "action": (f"{member}/{p.action.segment}", "post"),
    }[op]


# --------------------------------------------------------------------------- schemas


def field_schema(f: Field) -> Doc:
    """The schema of one field, from its kind."""
    kind = f.kind
    schema: Doc
    if kind == "str":
        schema = {"type": "string"}
    elif kind == "date":
        schema = {"type": "string", "format": "date"}
    elif kind == "dt":
        schema = {"type": "string", "format": "date-time"}
    elif kind == "int":
        schema = {"type": "integer", "minimum": 0}
    elif kind == "num":
        schema = {"type": "number"}
    elif kind == "ccy":
        schema = {"type": "string", "minLength": 3, "maxLength": 3}
    elif kind == "uri":
        schema = {"type": "string", "format": "uri"}
    elif kind.startswith("money:"):
        schema = {"type": "number", "minimum": 0, "maximum": int(kind.split(":")[1])}
    elif kind.startswith("enum:"):
        schema = {"type": "string", "enum": kind.split(":")[1].split("|")}
    else:
        raise ValueError(f"unknown field kind {kind!r}")
    schema["description"] = _sentence(f.description)
    return schema


def _object(description: str, required: list[str], properties: Doc) -> Doc:
    schema: Doc = {"type": "object", "description": _sentence(description)}
    if required:
        schema["required"] = required
    schema["properties"] = properties
    return schema


def _writable(state: State) -> list[Field]:
    return [f for f in state.fields if f.name != "status"]


def _action_schema_name(p: Product) -> str:
    return f"{_upper_first(p.action.operation_id)}Request"


def component_schemas(state: State) -> Doc:
    """All component schemas the operations of this state refer to."""
    p = state.product
    res, name = p.resource, p.type_name
    status_field = next(f for f in state.fields if f.name == "status")
    writable = _writable(state)
    resource_props: Doc = {"id": {"type": "string", "description": f"Identifier of the {res}."}}
    resource_props.update({f.name: field_schema(f) for f in state.fields})
    schemas: Doc = {
        name: _object(f"A {res}.", ["id", "status", writable[0].name], resource_props),
        f"{name}List": _object(
            f"A page of {p.plural}.",
            ["items"],
            {
                "items": {
                    "type": "array",
                    "items": {"$ref": f"#/components/schemas/{name}"},
                    "description": f"The {p.plural} on this page.",
                },
                "nextPageToken": {
                    "type": "string",
                    "description": "Token that fetches the next page. Absent on the last page.",
                },
            },
        ),
    }
    if "create" in state.ops:
        schemas[f"{name}Create"] = _object(
            f"Fields of a new {res}.",
            [f.name for f in writable[:2]],
            {f.name: field_schema(f) for f in writable[:4]},
        )
    if "update" in state.ops:
        schemas[f"{name}Update"] = _object(
            f"Fields of a {res} that can be changed.",
            [],
            {f.name: field_schema(f) for f in writable[1:4]},
        )
    action = p.action
    schemas[_action_schema_name(p)] = _object(
        f"Details of the request to {_lower_first(action.summary)}.",
        [action.body[0].name],
        {f.name: field_schema(f) for f in action.body},
    )
    if "search" in state.ops:
        schemas[f"{name}Search"] = _object(
            f"Filters of a {res} search. Every filter that is given must match.",
            [],
            {
                "status": field_schema(status_field),
                writable[0].name: field_schema(writable[0]),
                "createdAfter": {
                    "type": "string",
                    "format": "date-time",
                    "description": f"Only {p.plural} created after this instant.",
                },
            },
        )
    schemas["Problem"] = _object(
        "Error body returned for every failed call, with the application/problem+json media type.",
        ["type", "title", "status", "code", "detail"],
        {
            "type": {
                "type": "string",
                "format": "uri",
                "description": "URI that identifies the kind of problem.",
            },
            "title": {
                "type": "string",
                "description": "Short, human-readable summary of the problem.",
            },
            "status": {"type": "integer", "description": "HTTP status code of the response."},
            "code": {
                "type": "string",
                "description": f"Lab Bank error code, for example ERR-{p.prefix}-001.",
            },
            "detail": {
                "type": "string",
                "description": "Explanation specific to this occurrence of the problem.",
            },
            "correlationId": {
                "type": "string",
                "description": "Correlation identifier of the failed call.",
            },
        },
    )
    return schemas


# --------------------------------------------------------------------------- operations


def _ref(name: str) -> Doc:
    return {"$ref": f"#/components/schemas/{name}"}


def _problem() -> Doc:
    return {"application/problem+json": {"schema": _ref("Problem")}}


def _codes_for(state: State, op: str, status: int) -> list[ErrorCode]:
    own = [e for e in state.errors if e.op == op and e.status == status]
    if own:
        return own
    return [next(e for e in state.errors if e.status == status)]


def _error_description(state: State, op: str, status: int) -> str:
    res = state.product.resource
    parts = [f"`{e.code}` when {e.clause}" for e in _codes_for(state, op, status)]
    listing = parts[0] if len(parts) == 1 else "; ".join(parts[:-1]) + "; or " + parts[-1]
    return f"{_LEADS[status].format(resource=res)} The Problem `code` is {listing}."


def _success_description(p: Product, op: str) -> str:
    return {
        "list": f"A page of {p.plural}.",
        "get": f"The {p.resource}.",
        "create": f"The {p.resource} was created.",
        "update": f"The {p.resource} after the change.",
        "close": f"The {p.resource} was closed.",
        "action": f"The action was applied and the {p.resource} is returned.",
        "search": f"A page of {p.plural} that match the search.",
    }[op]


def _success_schema(p: Product, op: str) -> str:
    return f"{p.type_name}List" if op in ("list", "search") else p.type_name


def _responses(state: State, op: str) -> Doc:
    p = state.product
    responses: Doc = {}
    for status in OP_STATUSES[op]:
        key = str(status)
        if status in (200, 201):
            responses[key] = {
                "description": _success_description(p, op),
                "content": {"application/json": {"schema": _ref(_success_schema(p, op))}},
            }
        elif status == 401:
            responses[key] = {
                "description": "The access token is missing, invalid or expired. "
                "The Problem `code` is `AUTH-001`.",
                "content": _problem(),
            }
        elif status == 429:
            responses[key] = {
                "description": "Too many requests were sent and the call was refused. The Problem "
                "`code` is `RATE-001`. Wait for the number of seconds in the Retry-After header "
                "before trying again.",
                "headers": {
                    "Retry-After": {
                        "description": "Number of seconds to wait before retrying.",
                        "schema": {"type": "integer"},
                    }
                },
                "content": _problem(),
            }
        else:
            responses[key] = {
                "description": _error_description(state, op, status),
                "content": _problem(),
            }
    return responses


_IDEMPOTENT_NOUN = {"create": "creation", "update": "change", "action": "action"}


def _parameters(state: State, op: str) -> list[Doc]:
    p = state.product
    params: list[Doc] = []
    if op in ("get", "update", "close", "action"):
        params.append(
            {
                "name": p.id_param,
                "in": "path",
                "required": True,
                "description": f"Identifier of the {p.resource}.",
                "schema": {"type": "string"},
            }
        )
    if op == "list":
        status_field = next(f for f in state.fields if f.name == "status")
        params += [
            {
                "name": "pageSize",
                "in": "query",
                "required": False,
                "description": f"Number of {p.plural} to return on one page. The default is 20.",
                "schema": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": state.page_max,
                },
            },
            {
                "name": "pageToken",
                "in": "query",
                "required": False,
                "description": "Token from the previous page. Leave it out to start at the "
                "beginning.",
                "schema": {"type": "string"},
            },
            {
                "name": "status",
                "in": "query",
                "required": False,
                "description": f"Only return {p.plural} in this state.",
                "schema": {"type": "string", "enum": field_schema(status_field)["enum"]},
            },
        ]
    if op in ("create", "update", "action"):
        params.append(
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": op in state.idem_required,
                "description": "Unique key of up to 64 characters. A retried request with the same "
                f"key returns the original result instead of repeating the {_IDEMPOTENT_NOUN[op]}.",
                "schema": {"type": "string", "maxLength": 64},
            }
        )
    return params


def _request_body(state: State, op: str) -> Doc | None:
    p = state.product
    json_ref = _ref
    if op == "create":
        return {
            "required": True,
            "description": f"The {p.resource} to create.",
            "content": {"application/json": {"schema": json_ref(f"{p.type_name}Create")}},
        }
    if op == "update":
        return {
            "required": True,
            "description": f"The fields to change on the {p.resource}.",
            "content": {"application/json": {"schema": json_ref(f"{p.type_name}Update")}},
        }
    if op == "action":
        return {
            "required": True,
            "description": f"Details of the request to {_lower_first(p.action.summary)}.",
            "content": {"application/json": {"schema": json_ref(_action_schema_name(p))}},
        }
    if op == "search":
        return {
            "required": True,
            "description": f"Filters that every returned {p.resource} must match.",
            "content": {"application/json": {"schema": json_ref(f"{p.type_name}Search")}},
        }
    return None


def _summary_and_description(state: State, op: str) -> tuple[str, str]:
    p = state.product
    res, plural = p.resource, p.plural
    if op == "list":
        description = (
            f"Returns a page of {plural}, newest first. Use `pageSize` to choose how many come "
            f"back, up to {state.page_max}, and `pageToken` to fetch the next page."
        )
        if "list" in state.deprecated:
            description += (
                f" This operation is deprecated: use {operation_id(p, 'search')} instead."
            )
        return f"List {plural}", description
    texts = {
        "get": (
            f"Get a {res}",
            f"Returns one {res} by its identifier, with its current state and every field "
            f"described in the {p.type_name} schema.",
        ),
        "create": (
            f"Create a {res}",
            f"Creates a {res} for the authenticated customer. Send an `Idempotency-Key` header "
            f"so that a retried request does not create a second {res}.",
        ),
        "update": (
            f"Update a {res}",
            f"Changes the writable fields of a {res}. Fields that are left out stay as they are.",
        ),
        "close": (f"Close a {res}", f"Closes a {res}. A closed {res} cannot be reopened."),
        "action": (p.action.summary, p.action.description),
        "search": (
            f"Search {plural}",
            f"Finds {plural} that match every filter in the request body. Use it instead of "
            f"listing when you need to filter by more than one field.",
        ),
    }
    summary, description = texts[op]
    return summary, _sentence(description)


def _operation(state: State, op: str) -> Doc:
    p = state.product
    summary, description = _summary_and_description(state, op)
    result: Doc = {
        "operationId": operation_id(p, op),
        "summary": summary,
        "description": description,
    }
    if op in state.deprecated:
        result["deprecated"] = True
    result["tags"] = [p.title]
    result["security"] = [{"bearerAuth": [state.role_scope(ROLE_OF_OP[op])], "apiKey": []}]
    params = _parameters(state, op)
    if params:
        result["parameters"] = params
    body = _request_body(state, op)
    if body is not None:
        result["requestBody"] = body
    result["responses"] = _responses(state, op)
    return result


# --------------------------------------------------------------------------- the document


def render(state: State) -> Doc:
    """The OpenAPI document of one product version."""
    p = state.product
    scope_names = [n for n, _ in state.scopes]
    scope_list = ", ".join(scope_names[:-1]) + f" and {scope_names[-1]}"
    paths: Doc = {}
    for op in state.ops:
        path, method = op_path(state, op)
        paths.setdefault(path, {})[method] = _operation(state, op)
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"Lab Bank {p.title} API (v{state.version})",
            "version": f"{state.version}.0.0",
            "description": f"{p.blurb}. This is version {state.version} of the {p.title} API. "
            f"The scopes are {scope_list}. {DISCLAIMER}",
        },
        "servers": [{"url": SERVER}],
        "tags": [{"name": p.title, "description": f"Operations on {p.plural}."}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "oauth2",
                    "description": f"Access token for the {p.title} API, obtained from the token "
                    "endpoint of the Authentication API with the client credentials grant and "
                    "sent as `Authorization: Bearer <token>`. Each operation lists the scope it "
                    "needs.",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": TOKEN_URL,
                            "scopes": dict(state.scopes),
                        }
                    },
                },
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Api-Key",
                    "description": API_KEY_TEXT,
                },
            },
            "schemas": component_schemas(state),
        },
    }


# --------------------------------------------------------------------------- locating elements


def _find_op(doc: Mapping[str, Any], op_id: str) -> tuple[str, str]:
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if operation["operationId"] == op_id:
                return str(path), str(method)
    raise KeyError(op_id)


def _param_index(operation: Mapping[str, Any], name: str) -> int:
    return next(i for i, prm in enumerate(operation["parameters"]) if prm["name"] == name)


def first_response_with(doc: Mapping[str, Any], code: str) -> str:
    """The JSON Pointer of the first response whose description names ``code``."""
    needle = f"`{code}`"
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            for status, response in operation["responses"].items():
                if needle in response["description"]:
                    return pointer("paths", path, method, "responses", status)
    raise KeyError(code)


def locate(doc: Doc, state: State, probe: tuple[str, ...]) -> str:
    """The JSON Pointer, in the rendered document, of a recorded change."""
    p = state.product
    kind = probe[0]
    if kind == "schema_property":
        return pointer("components", "schemas", p.type_name, "properties", probe[1])
    if kind == "page_size":
        path, method = _find_op(doc, operation_id(p, "list"))
        index = _param_index(doc["paths"][path][method], "pageSize")
        return pointer("paths", path, method, "parameters", index, "schema", "maximum")
    if kind == "amount_max":
        return pointer("components", "schemas", p.type_name, "properties", probe[1], "maximum")
    if kind == "idempotency":
        path, method = _find_op(doc, operation_id(p, probe[1]))
        index = _param_index(doc["paths"][path][method], "Idempotency-Key")
        return pointer("paths", path, method, "parameters", index, "required")
    if kind == "operation":
        path, method = _find_op(doc, operation_id(p, probe[1]))
        return pointer("paths", path, method)
    if kind == "deprecated":
        path, method = _find_op(doc, operation_id(p, probe[1]))
        return pointer("paths", path, method, "deprecated")
    if kind == "error":
        return first_response_with(doc, probe[1])
    if kind == "scope":
        return pointer(
            "components",
            "securitySchemes",
            "bearerAuth",
            "flows",
            "clientCredentials",
            "scopes",
            probe[1],
        )
    raise ValueError(f"unknown probe {probe}")
