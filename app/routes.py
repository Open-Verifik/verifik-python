from fastapi import APIRouter

from app.repositories.catalog import catalog_route
from app.repositories.cedula.routes import cedula_route
from app.repositories.health.routes import health_route
from app.repositories.home.routes import home_route
from app.repositories.sispro.routes import sispro_route


def register(router: APIRouter) -> None:
    home_route.register(router)
    health_route.register(router)
    sispro_route.register(router)
    cedula_route.register(router)
    catalog_route.register(router)
