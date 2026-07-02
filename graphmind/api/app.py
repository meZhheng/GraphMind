from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from graphmind.api.routes import router
from graphmind.core.config import STATIC_DIR


def create_app() -> FastAPI:
    app = FastAPI(title="GraphMind Agent Service")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app
