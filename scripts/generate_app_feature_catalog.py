"""Build a slim catalog from verifik-backend/scripts/app-features-final.json."""

from __future__ import annotations

import json
from pathlib import Path

BACKEND_JSON = Path("/Users/miguel/verifik/verifik-backend/scripts/app-features-final.json")
OUTPUT = (
    Path(__file__).resolve().parents[1] / "app" / "repositories" / "catalog" / "app_features.json"
)

FIRST_CLASS_PATHS = {"/v2/co/cedula", "/v2/co/afiliaciones"}
KEEP_DEP_KEYS = (
    "field",
    "type",
    "required",
    "enum",
    "min",
    "max",
    "description",
    "dependencyGroup",
    "dateFormat",
    "requiredWhen",
)


def normalize_url(url: str) -> str:
    return "/" + str(url).lstrip("/")


def slim_dependency(dep: dict) -> dict:
    return {key: dep[key] for key in KEEP_DEP_KEYS if key in dep and dep[key] is not None}


def pick_preferred(candidates: list[dict]) -> dict:
    return sorted(
        candidates,
        key=lambda item: (
            not bool(item.get("isAvailable", True)),
            not bool(item.get("smartCheckEnabled")),
            item.get("code") or "",
        ),
    )[0]


def slim_feature(feature: dict) -> dict:
    method = str(feature.get("method") or "GET").upper()
    return {
        "code": feature["code"],
        "name": feature.get("name") or feature["code"],
        "url": normalize_url(feature["url"]),
        "method": method,
        "country": feature.get("country") or "world",
        "dependencies": [
            slim_dependency(dep) for dep in feature.get("dependencies") or [] if dep.get("field")
        ],
    }


def build_catalog(features: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}

    for feature in features:
        url = feature.get("url")
        if not url or "@" in str(url):
            continue

        path = normalize_url(url)
        if path in FIRST_CLASS_PATHS:
            continue

        method = str(feature.get("method") or "GET").upper()
        grouped.setdefault((method, path), []).append(feature)

    catalog = [slim_feature(pick_preferred(items)) for items in grouped.values()]
    catalog.sort(key=lambda item: (item["url"], item["method"], item["code"]))
    return catalog


def main() -> None:
    features = json.loads(BACKEND_JSON.read_text())
    catalog = build_catalog(features)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(catalog)} features to {OUTPUT}")


if __name__ == "__main__":
    main()
