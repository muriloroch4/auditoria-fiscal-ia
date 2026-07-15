from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .schema_loader import load_json_schema

try:
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover - exercised in dependency-free local runtimes.
    _jsonschema = None


class SchemaValidationError(ValueError):
    pass


def validate_payload_against_schema(payload: Any, schema_name: str) -> None:
    schema = load_json_schema(schema_name)
    validate_payload(payload, schema)


def validate_payload(payload: Any, schema: dict[str, Any]) -> None:
    if _jsonschema is not None:
        try:
            _jsonschema.Draft202012Validator(schema).validate(payload)
        except _jsonschema.ValidationError as exc:
            path = "$" + "".join(f".{part}" if isinstance(part, str) else f"[{part}]" for part in exc.path)
            raise SchemaValidationError(f"{path}: {exc.message}") from exc
        return

    _validate(payload, schema, schema, "$")


def _validate(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(root, str(schema["$ref"])), root, path)
        return

    for child_schema in schema.get("allOf", []):
        if isinstance(child_schema, dict):
            _validate(value, child_schema, root, path)

    if "anyOf" in schema:
        errors = _collect_combinator_errors(value, schema["anyOf"], root, path)
        if len(errors) == len(schema["anyOf"]):
            detail = "; ".join(errors[:3])
            raise SchemaValidationError(f"{path}: valor nao atende a nenhuma alternativa anyOf ({detail})")

    if "oneOf" in schema:
        errors = _collect_combinator_errors(value, schema["oneOf"], root, path)
        valid_count = len(schema["oneOf"]) - len(errors)
        if valid_count != 1:
            raise SchemaValidationError(f"{path}: valor deve atender exatamente uma alternativa oneOf; validas: {valid_count}")

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path}: esperado valor constante {schema['const']!r}; recebido {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: valor {value!r} fora do enum permitido")

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise SchemaValidationError(f"{path}: tipo invalido; esperado {expected_type!r}")

    if isinstance(value, dict):
        _validate_object(value, schema, root, path)
    elif isinstance(value, list):
        _validate_array(value, schema, root, path)
    elif isinstance(value, str):
        _validate_string(value, schema, path)
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        _validate_number(value, schema, path)


def _collect_combinator_errors(value: Any, schemas: list[Any], root: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for child_schema in schemas:
        if not isinstance(child_schema, dict):
            continue
        try:
            _validate(value, child_schema, root, path)
        except SchemaValidationError as exc:
            errors.append(str(exc))
    return errors


def _validate_object(value: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in value:
            raise SchemaValidationError(f"{path}: propriedade obrigatoria ausente: {key}")

    properties = schema.get("properties", {})
    for key, child_schema in properties.items():
        if key in value:
            _validate(value[key], child_schema, root, f"{path}.{key}")

    additional = schema.get("additionalProperties", True)
    extra_keys = [key for key in value if key not in properties]
    if additional is False and extra_keys:
        raise SchemaValidationError(f"{path}: propriedades nao permitidas: {', '.join(sorted(extra_keys))}")
    if isinstance(additional, dict):
        for key in extra_keys:
            _validate(value[key], additional, root, f"{path}.{key}")


def _validate_array(value: list[Any], schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    if "minItems" in schema and len(value) < schema["minItems"]:
        raise SchemaValidationError(f"{path}: quantidade de itens menor que o minimo {schema['minItems']}")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        raise SchemaValidationError(f"{path}: quantidade de itens maior que o maximo {schema['maxItems']}")

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            _validate(item, item_schema, root, f"{path}[{index}]")


def _validate_string(value: str, schema: dict[str, Any], path: str) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        raise SchemaValidationError(f"{path}: texto menor que o tamanho minimo {schema['minLength']}")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        raise SchemaValidationError(f"{path}: texto maior que o tamanho maximo {schema['maxLength']}")
    if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
        raise SchemaValidationError(f"{path}: texto nao atende ao padrao {schema['pattern']!r}")


def _validate_number(value: int | float | Decimal, schema: dict[str, Any], path: str) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise SchemaValidationError(f"{path}: valor menor que o minimo {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        raise SchemaValidationError(f"{path}: valor maior que o maximo {schema['maximum']}")


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    return True


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"Referencia externa nao suportada: {ref}")
    current: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise SchemaValidationError(f"Referencia invalida: {ref}")
        current = current[part]
    if not isinstance(current, dict):
        raise SchemaValidationError(f"Referencia invalida: {ref}")
    return current
