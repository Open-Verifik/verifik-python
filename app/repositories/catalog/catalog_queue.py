LEGACY_QUEUE_SPECS = {
    "colombia_api_identity_lookup": {
        "queueKey": "co.cedula.queue",
        "name": "Queue Cedula",
        "country": "CO",
    },
    "colombia_api_affiliations": {
        "queueKey": "co.sispro.queue",
        "name": "Queue SISPRO",
        "legacyName": "SISPRO Queue",
        "country": "CO",
    },
}

STRIP_KEYS = {"type", "includeCost", "token"}


def queue_spec(feature: dict) -> dict:
    legacy = LEGACY_QUEUE_SPECS.get(feature["code"])

    if legacy:
        return {**legacy, "featureCode": feature["code"]}

    return {
        "queueKey": f"{feature['code']}.queue",
        "name": f"Queue {feature['name']}",
        "featureCode": feature["code"],
        "country": feature.get("country") or "world",
    }


def input_data(params: dict) -> dict:
    return {
        key: value
        for key, value in params.items()
        if key not in STRIP_KEYS and value not in (None, "")
    }


def batch_name(feature: dict, params: dict) -> str:
    spec = queue_spec(feature)
    hint = (
        params.get("documentNumber")
        or params.get("plate")
        or params.get("fullName")
        or params.get("name")
        or ""
    )
    return f"{spec['name']} {hint}".strip()
