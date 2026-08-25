import json
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("app_features.json")


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text())


def find_feature(method: str, path: str) -> dict | None:
    method = method.upper()
    for feature in load_catalog():
        if feature["method"] == method and feature["url"] == path:
            return feature
    return None
