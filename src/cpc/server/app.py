"""FastAPI application entry point for the CPC server."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cpc.config import ServerConfig
from cpc.server.api import router, set_engine
from cpc.server.mhng_engine import MHNGEngine
from cpc.server.sample_store import SampleStore


def create_app(config: ServerConfig | None = None) -> FastAPI:
    if config is None:
        config = ServerConfig()

    app = FastAPI(title="CPC Platform", version="0.1.0")

    # CORS for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize Supabase if configured
    sb = None
    if config.supabase_url and config.supabase_key:
        from supabase import create_client
        sb = create_client(config.supabase_url, config.supabase_key)

    store = SampleStore(sb=sb)
    engine = MHNGEngine(sample_store=store, sb=sb)
    set_engine(engine)

    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "backend": "supabase" if sb else "memory"}

    return app


def main() -> None:
    config = ServerConfig()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
