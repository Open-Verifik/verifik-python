from fastapi import HTTPException

from app.repositories.home.modules.home_module import README_PATH


def ensure_readme() -> None:
    if not README_PATH.exists():
        raise HTTPException(status_code=404, detail="README.md not found")
