import httpx

from app.clients.verifik import AFILIACIONES_PATH, get_verifik_client
from app.core.http_handler import ApiError


def get(params: dict, authorization: str) -> tuple[int, dict]:
    query = {key: value for key, value in params.items() if key != "type"}

    try:
        with get_verifik_client() as client:
            response = client.get(
                AFILIACIONES_PATH,
                params=query,
                headers={"Authorization": authorization},
            )
            body = response.json()
    except httpx.TimeoutException as exception:
        raise ApiError("504") from exception
    except httpx.RequestError as exception:
        raise ApiError(f"503:{exception}") from exception
    except ValueError as exception:
        raise ApiError(f"503:{exception}") from exception

    if not isinstance(body, dict):
        raise ApiError("503")

    return response.status_code, body
