from pydantic import BaseModel


class HomePage(BaseModel):
    title: str
    html: str
