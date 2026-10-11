from typing import Any

import jsonschema


class SchemaValidationError(Exception):
    pass


def validate_response_schema(response_body: Any, schema: dict[str, Any]) -> list[str]:
    """
    Validates a response body against a JSON Schema (Draft 7 / OpenAPI 3.0/3.1 compatible).
    Returns list of error descriptions (empty if valid).
    """
    errors: list[str] = []
    try:
        validator = jsonschema.Draft7Validator(schema)
        for err in validator.iter_errors(response_body):
            path_str = ".".join(str(p) for p in err.absolute_path) or "root"
            errors.append(f"At {path_str}: {err.message}")
    except Exception as e:
        errors.append(f"Schema validator error: {e!s}")
    return errors


def extract_response_schema(
    openapi_doc: dict[str, Any], operation_id: str, status_code: int
) -> dict[str, Any] | None:
    """
    Looks up the response schema for a given operation_id and HTTP status code in an OpenAPI document.
    """
    paths = openapi_doc.get("paths", {})
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            if operation.get("operationId") == operation_id:
                responses = operation.get("responses", {})
                resp = responses.get(str(status_code)) or responses.get("default")
                if resp and isinstance(resp, dict):
                    content = resp.get("content", {})
                    json_media = content.get("application/json", {})
                    return json_media.get("schema")
    return None
