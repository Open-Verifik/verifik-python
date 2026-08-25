import json

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.catalog import catalog_loader, catalog_queue
from app.repositories.proxy.modules import proxy_module
from app.repositories.sispro.modules import smart_batch_module

client = TestClient(app)

PERU_QUERY = {"documentType": "DNI", "documentNumber": "12345678"}


def test_catalog_registers_supported_urls() -> None:
    catalog = catalog_loader.load_catalog()
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]

    assert len(catalog) >= 200
    assert "/v2/pe/cedula" in paths
    assert "/v2/dea" in paths
    assert "/v2/co/cedula" in paths
    assert "/v2/co/afiliaciones" in paths
    assert paths["/v2/co/cedula"]["get"]["tags"] == ["cedula"]
    assert "type" in {param["name"] for param in paths["/v2/pe/cedula"]["get"]["parameters"]}


def test_catalog_queue_spec_uses_feature_code() -> None:
    spec = catalog_queue.queue_spec(
        {
            "code": "peru_identity_lookup",
            "name": "Peru - National ID Verification",
            "country": "Peru",
        }
    )

    assert spec["queueKey"] == "peru_identity_lookup.queue"
    assert spec["featureCode"] == "peru_identity_lookup"


def test_peru_cedula_requires_authorization() -> None:
    response = client.get("/v2/pe/cedula", params=PERU_QUERY)

    assert response.status_code == 401


def test_peru_cedula_requires_document_type() -> None:
    response = client.get(
        "/v2/pe/cedula",
        params={"documentNumber": "12345678"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "MissingParameter"


def test_peru_cedula_forwards_sync(monkeypatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"data": {"documentNumber": "12345678"}, "signature": "abc"},
        )

    monkeypatch.setattr(
        proxy_module,
        "get_verifik_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test"),
    )

    response = client.get(
        "/v2/pe/cedula",
        params=PERU_QUERY,
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 200
    assert captured["path"] == "/v2/pe/cedula"
    assert captured["authorization"] == "Bearer test-jwt"


def test_peru_cedula_queue_posts_from_queue(monkeypatch) -> None:
    posted = {}
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v2/smart-batches/from-queue":
            posted["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "queued",
                        "batchId": "batch-pe-1",
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
        "/v2/pe/cedula",
        params={**PERU_QUERY, "type": "queue"},
        headers={"Authorization": "Bearer test-jwt"},
    )

    assert response.status_code == 202
    assert response.json()["batchId"] == "batch-pe-1"
    assert "/v2/pe/cedula" not in calls
    assert posted["body"]["queueKey"] == "peru_identity_lookup.queue"
    assert posted["body"]["featureCode"] == "peru_identity_lookup"
    assert posted["body"]["inputData"]["documentNumber"] == "12345678"
