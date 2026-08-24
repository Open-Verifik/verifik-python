from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_renders_readme() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "verifik-smartcheck" in response.text
    assert "home_route.py" in response.text
