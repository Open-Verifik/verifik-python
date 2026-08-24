from app.core.http_handler import ApiError, error_handler


def test_error_handler_maps_prefixed_message() -> None:
    error = error_handler(Exception("404:README.md not found"))

    assert error.status == 404
    assert error.code == "NotFound"
    assert error.message == "README.md not found"


def test_error_handler_defaults_unknown_errors_to_500() -> None:
    error = error_handler(Exception("something broke"))

    assert error.status == 500
    assert error.code == "InternalServerError"


def test_error_handler_maps_401() -> None:
    error = error_handler(Exception("401"))

    assert error.status == 401
    assert error.code == "Unauthorized"


def test_error_handler_maps_412_with_detail() -> None:
    error = error_handler(Exception("412:missing_otp"))

    assert error.status == 412
    assert error.code == "PreconditionFailed"
    assert error.message == "missing_otp"


def test_error_handler_allows_api_error_code_override() -> None:
    error = error_handler(ApiError("409:documentType is required", code="MissingParameter"))

    assert error.status == 409
    assert error.code == "MissingParameter"
    assert error.message == "documentType is required"
