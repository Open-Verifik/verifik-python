import httpx

from app.clients.verifik import get_verifik_client
from app.core.http_handler import ApiError

HOP_BY_HOP = {"host", "content-length", "transfer-encoding", "connection"}


def _headers(authorization: str) -> dict:
    return {"Authorization": authorization}


def forward(method: str, path: str, authorization: str, params: dict, body: dict | None) -> tuple[int, dict]:
    try:
        with get_verifik_client() as client:
            kwargs: dict = {"headers": _headers(authorization), "params": params}
            if method.upper() not in {"GET", "HEAD", "DELETE"} and body is not None:
                kwargs["json"] = body

            response = client.request(method, path, **kwargs)
            payload = response.json()
    except httpx.TimeoutException as exception:
        raise ApiError("504") from exception
    except httpx.RequestError as exception:
        raise ApiError(f"503:{exception}") from exception
    except ValueError as exception:
        raise ApiError(f"503:{exception}") from exception

    if not isinstance(payload, dict):
        raise ApiError("503")

    return response.status_code, payload
