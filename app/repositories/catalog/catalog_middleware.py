from datetime import datetime

from fastapi import Request

from app.core.http_handler import ApiError

REQUEST_TYPES = {"sync", "queue"}
DATE_FORMATS = {
    "dd/MM/yyyy": "%d/%m/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "yyyy-MM-dd": "%Y-%m-%d",
    "YYYY-MM-DD": "%Y-%m-%d",
}


def require_authorization(request: Request) -> None:
    header = request.headers.get("authorization")

    if not header or not header.lower().startswith("bearer "):
        raise ApiError("401")

    if not header[7:].strip():
        raise ApiError("401")

    request.state.authorization = header


def _missing(field: str) -> None:
    raise ApiError(f"409:{field} is required", code="MissingParameter")


def _validate_type(values: dict) -> None:
    request_type = values.get("type")

    if request_type and request_type not in REQUEST_TYPES:
        raise ApiError("409:type must be sync or queue", code="MissingParameter")


def _has_value(values: dict, field: str) -> bool:
    value = values.get(field)
    return value not in (None, "")


def _group_complete(group: str, dependencies: list[dict], values: dict) -> bool:
    members = [dep for dep in dependencies if dep.get("dependencyGroup") == group]
    return bool(members) and all(_has_value(values, dep["field"]) for dep in members)


def _validate_groups(dependencies: list[dict], values: dict) -> None:
    groups = {dep.get("dependencyGroup") for dep in dependencies if dep.get("dependencyGroup")}

    if groups and not any(_group_complete(group, dependencies, values) for group in groups):
        raise ApiError("409:provide a complete parameter group", code="MissingParameter")


def _validate_required_when(dep: dict, values: dict) -> None:
    rule = dep.get("requiredWhen")

    if not rule:
        return

    trigger = values.get(rule.get("field")) in (rule.get("in") or [])

    if trigger and not _has_value(values, dep["field"]):
        _missing(dep["field"])


def _validate_constraints(dep: dict, value: object) -> None:
    field = dep["field"]
    text = str(value)

    if dep.get("enum") and text not in [str(item) for item in dep["enum"]]:
        raise ApiError(f"409:{field} is invalid", code="MissingParameter")

    if dep.get("type") != "Number":
        if dep.get("min") is not None and len(text) < int(dep["min"]):
            raise ApiError(f"409:{field} is too short", code="MissingParameter")
        if dep.get("max") is not None and len(text) > int(dep["max"]):
            raise ApiError(f"409:{field} is too long", code="MissingParameter")

    pattern = DATE_FORMATS.get(dep.get("dateFormat") or "")
    if pattern:
        try:
            datetime.strptime(text, pattern)
        except ValueError as exception:
            message = f"409:{field} must match {dep['dateFormat']}"
            raise ApiError(message, code="MissingParameter") from exception


def validate_feature(feature: dict, values: dict) -> None:
    dependencies = feature.get("dependencies") or []
    _validate_type(values)
    _validate_groups(dependencies, values)

    for dep in dependencies:
        field = dep["field"]

        if dep.get("required") and not _has_value(values, field):
            _missing(field)

        _validate_required_when(dep, values)

        if not _has_value(values, field):
            continue

        _validate_constraints(dep, values[field])
