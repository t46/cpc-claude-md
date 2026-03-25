"""FastAPI application entry point for the CPC server."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from cpc.config import ServerConfig
from cpc.server.api import router, set_engine
from cpc.server.mhng_engine import MHNGEngine
from cpc.server.sample_store import SampleStore


def create_app(config: ServerConfig | None = None) -> FastAPI:
    if config is None:
        config = ServerConfig()

    app = FastAPI(title="CPC Platform", version="0.1.0")

    store = SampleStore(data_dir=config.data_dir)
    engine = MHNGEngine(sample_store=store)
    set_engine(engine)

    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def main() -> None:
    config = ServerConfig()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
