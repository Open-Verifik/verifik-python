import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.sispro.modules import sispro_module, sispro_queue_worker, smart_batch_module

client = TestClient(app)

VALID_QUERY = {
    "documentType": "CC",
    "documentNumber": "1032386359",
    "date": "01/01/1990",
}

SUPRE_OK_RECORDS = [
    {"documentType": "CC", "documentNumber": "1007463534", "date": "09/05/2008"},
    {"documentType": "CC", "documentNumber": "1064118303", "date": "03/07/2014"},
    {"documentType": "CC", "documentNumber": "1003005729", "date": "27/09/2019"},
    {"documentType": "CC", "documentNumber": "32288038", "date": "14/05/1987"},
    {"documentType": "CC", "documentNumber": "1067592151", "date": "29/06/2022"},
]


def test_sispro_requires_authorization() -> None:
    response = client.get("/v2/co/afiliaciones", params=VALID_QUERY)

    assert response.status_code == 401
    assert response.json() == {"code": "Unauthorized", "message": "Unauthorized"}


def test_sispro_rejects_invalid_document_type() -> None:
    response = client.get(
        "/v2/co/afiliaciones",
        params={**VALID_QUERY, "documentType": "XX"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


def test_sispro_rejects_invalid_date() -> None:
    response = client.get(
        "/v2/co/afiliaciones",
        params={**VALID_QUERY, "date": "1990-01-01"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"
    assert "DD/MM/YYYY" in response.json()["message"]


@pytest.mark.parametrize("record", SUPRE_OK_RECORDS, ids=lambda row: row["documentNumber"])
def test_sispro_forwards_supre_ok_records(monkeypatch, record: dict) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["url"] = str(request.url)

        return httpx.Response(
            200,
            json={"data": {"documentNumber": record["documentNumber"]}, "signature": "abc"},
        )

    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/afiliaciones",
        params=record,
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 200
    assert record["documentNumber"] in captured["url"]
    encoded_date = record["date"].replace("/", "%2F")
    assert encoded_date in captured["url"] or record["date"] in captured["url"]
    assert captured["authorization"] == "Bearer test-jwt"
    assert response.json()["data"]["documentNumber"] == record["documentNumber"]


def test_sispro_forwards_bearer_and_returns_node_body(monkeypatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["path"] = request.url.path

        return httpx.Response(200, json={"data": {"fullName": "TEST"}, "signature": "abc"})

    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/afiliaciones",
        params=VALID_QUERY,
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 200
    assert response.json() == {"data": {"fullName": "TEST"}, "signature": "abc"}
    assert captured["authorization"] == "Bearer test-jwt"
    assert captured["path"] == "/v2/co/afiliaciones"


def test_sispro_openapi_documents_jwt_and_query() -> None:
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/v2/co/afiliaciones"]["get"]
    query_names = {param["name"] for param in operation["parameters"] if param["in"] == "query"}

    assert {"documentType", "documentNumber", "date", "force", "audit", "type"} <= query_names
    assert operation.get("security")


def test_sispro_maps_timeout_to_504(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/afiliaciones",
        params=VALID_QUERY,
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 504
    assert response.json()["code"] == "Timeout"


def test_sispro_rejects_invalid_type() -> None:
    response = client.get(
        "/v2/co/afiliaciones",
        params={**VALID_QUERY, "type": "async"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


def test_sispro_queue_returns_202_without_calling_sispro(monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)

        if request.url.path == "/v2/smart-batches/from-queue":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "queued",
                        "batchId": "batch-1",
                        "rowIndex": 0,
                        "attemptCount": 0,
                    }
                },
            )

        if request.url.path == "/v2/smart-batches/queue/next":
            return httpx.Response(200, json={"data": None})

        raise AssertionError(f"unexpected Node path {request.url.path}")

    monkeypatch.setattr(
        smart_batch_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )
    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/co/afiliaciones",
        params={**VALID_QUERY, "type": "queue"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "batchId": "batch-1",
        "rowIndex": 0,
        "attemptCount": 0,
    }
    assert "/v2/co/afiliaciones" not in calls
    assert "/v2/smart-batches/from-queue" in calls


def test_sispro_worker_posts_success_attempt(monkeypatch) -> None:
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/co/afiliaciones":
            return httpx.Response(
                200,
                json={"data": {"documentNumber": "1007463534"}, "signature": "abc"},
            )

        if request.method == "POST" and request.url.path.endswith("/attempts"):
            posted["path"] = request.url.path
            posted["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": {}})

        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )
    monkeypatch.setattr(
        smart_batch_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    sispro_queue_worker.execute_and_record(
        "Bearer test-jwt",
        {
            "batchId": "batch-1",
            "rowIndex": 0,
            "inputData": SUPRE_OK_RECORDS[0],
        },
    )

    assert posted["path"] == "/v2/smart-batches/batch-1/rows/0/attempts"
    assert posted["body"]["status"] == "completed"
    assert posted["body"]["results"]["1"]["documentNumber"] == "1007463534"


def test_sispro_worker_posts_failed_attempt_on_404(monkeypatch) -> None:
    posted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/co/afiliaciones":
            return httpx.Response(404, json={"code": "NotFound", "message": "Record not found."})

        if request.method == "POST" and request.url.path.endswith("/attempts"):
            posted["body"] = json.loads(request.content)
            return httpx.Response(200, json={"data": {}})

        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    monkeypatch.setattr(
        sispro_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )
    monkeypatch.setattr(
        smart_batch_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    sispro_queue_worker.execute_and_record(
        "Bearer test-jwt",
        {"batchId": "batch-1", "rowIndex": 0, "inputData": VALID_QUERY},
    )

    assert posted["body"]["status"] == "failed"
    assert posted["body"]["statusCode"] == 404
    assert posted["body"]["code"] == "NotFound"
