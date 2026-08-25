import httpx

from app.clients.verifik import CEDULA_PATH, get_verifik_client
from app.core.http_handler import ApiError

# Second product on the generic from-queue API.
CEDULA_QUEUE = {
    "queueKey": "co.cedula.queue",
    "name": "Queue Cedula",
    "featureCode": "colombia_api_identity_lookup",
    "country": "CO",
}


def get(params: dict, authorization: str) -> tuple[int, dict]:
    query = {key: value for key, value in params.items() if key != "type"}

    try:
        with get_verifik_client() as client:
            response = client.get(
                CEDULA_PATH,
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
