import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.cedula.modules import cedula_module
from app.repositories.sispro.modules import smart_batch_module

client = TestClient(app)

VALID_QUERY = {
    "documentType": "CC",
    "documentNumber": "56097217",
}

CACHED_NUMBERS = [
    "56097217",
    "63535790",
    "1023942104",
    "34503117",
    "49716272",
    "64585026",
]


def test_cedula_requires_authorization() -> None:
    response = client.get("/v2/co/cedula", params=VALID_QUERY)

    assert response.status_code == 401
    assert response.json() == {"code": "Unauthorized", "message": "Unauthorized"}


def test_cedula_rejects_invalid_document_type() -> None:
    response = client.get(
        "/v2/co/cedula",
        params={**VALID_QUERY, "documentType": "CE"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


def test_cedula_rejects_short_document_number() -> None:
    response = client.get(
        "/v2/co/cedula",
        params={"documentType": "CC", "documentNumber": "1234"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


def test_cedula_rejects_invalid_type() -> None:
    response = client.get(
        "/v2/co/cedula",
        params={**VALID_QUERY, "type": "async"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


@pytest.mark.parametrize("document_number", CACHED_NUMBERS)
def test_cedula_forwards_cached_records(monkeypatch, document_number: str) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        captured["path"] = request.url.path

        return httpx.Response(
            200,
            json={"data": {"documentNumber": document_number}, "signature": "abc"},
        )

    monkeypatch.setattr(
        cedula_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/cedula",
        params={"documentType": "CC", "documentNumber": document_number},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 200
    assert captured["path"] == "/v2/co/cedula"
    assert document_number in captured["url"]
    assert captured["authorization"] == "Bearer test-jwt"
    assert response.json()["data"]["documentNumber"] == document_number


def test_cedula_forwards_bearer_and_returns_node_body(monkeypatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["path"] = request.url.path

        return httpx.Response(200, json={"data": {"fullName": "TEST"}, "signature": "abc"})

    monkeypatch.setattr(
        cedula_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/cedula",
        params=VALID_QUERY,
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 200
    assert response.json() == {"data": {"fullName": "TEST"}, "signature": "abc"}
    assert captured["authorization"] == "Bearer test-jwt"
    assert captured["path"] == "/v2/co/cedula"


def test_cedula_openapi_documents_jwt_and_query() -> None:
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/v2/co/cedula"]["get"]
    query_names = {param["name"] for param in operation["parameters"] if param["in"] == "query"}

    assert {"documentType", "documentNumber", "type"} <= query_names
    assert operation.get("security")


def test_cedula_queue_returns_202_without_calling_cedula(monkeypatch) -> None:
    calls: list[str] = []
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)

        if request.url.path == "/v2/smart-batches/from-queue":
            posted["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "queued",
                        "batchId": "batch-cedula-1",
                        "rowIndex": 0,
                        "attemptCount": 0,
                    }
                },
            )

        if request.url.path in {
            "/v2/smart-batches/queue/next",
            "/v2/internal/smart-batches/queue/next",
        }:
            return httpx.Response(200, json={"data": None})

        raise AssertionError(f"unexpected Node path {request.url.path}")

    monkeypatch.setattr(smart_batch_module, "claim_next_hmac", lambda: None)
    monkeypatch.setattr(
        smart_batch_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )
    monkeypatch.setattr(
        cedula_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/cedula",
        params={**VALID_QUERY, "type": "queue"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "batchId": "batch-cedula-1",
        "rowIndex": 0,
        "attemptCount": 0,
    }
    assert "/v2/co/cedula" not in calls
    assert "/v2/co/afiliaciones" not in calls
    assert "/v2/smart-batches/from-queue" in calls
    assert posted["body"]["queueKey"] == "co.cedula.queue"
    assert posted["body"]["featureCode"] == "colombia_api_identity_lookup"
    assert posted["body"]["inputData"]["documentNumber"] == VALID_QUERY["documentNumber"]
    assert posted["body"]["inputData"]["documentType"] == "CC"


@pytest.mark.parametrize("document_number", CACHED_NUMBERS)
def test_cedula_queue_posts_cached_number_in_from_queue(monkeypatch, document_number: str) -> None:
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/smart-batches/from-queue":
            posted["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "queued",
                        "batchId": f"batch-{document_number}",
                        "rowIndex": 0,
                        "attemptCount": 0,
                    }
                },
            )

        raise AssertionError(f"unexpected Node path {request.url.path}")

    monkeypatch.setattr(smart_batch_module, "claim_next_hmac", lambda: None)
    monkeypatch.setattr(
        smart_batch_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/cedula",
        params={"documentType": "CC", "documentNumber": document_number, "type": "queue"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 202
    assert posted["body"]["queueKey"] == "co.cedula.queue"
    assert posted["body"]["inputData"]["documentNumber"] == document_number
