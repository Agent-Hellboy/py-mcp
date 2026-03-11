"""FastAPI app factory for the layered runtime."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from ..middleware import MiddlewareConfig, setup_middleware
from ..registries.registry import RegistryManager, prompt_registry, resource_registry, tool_registry
from ..server import router
from ..session.store import SessionManager
from ..settings import ServerSettings


def create_app(
    middleware_config: Optional[MiddlewareConfig] = None,
    server_settings: Optional[ServerSettings] = None,
    **kwargs,
):
    app = FastAPI(title="py-mcp", summary="Composable MCP server on FastAPI")
    app.state.server_settings = server_settings or ServerSettings(
        name=kwargs.get("server_name", "py-mcp"),
        version=kwargs.get("server_version", "0.2.0"),
    )
    app.state.registry_manager = RegistryManager()
    app.state.registry_manager.copy_from_global_registries(
        tool_registry,
        prompt_registry,
        resource_registry,
    )
    app.state.session_manager = SessionManager()

    config = middleware_config or MiddlewareConfig(
        cors=kwargs.get("cors"),
        logging=kwargs.get("logging"),
        error_handling=kwargs.get("error_handling"),
        compression=kwargs.get("compression"),
        custom=kwargs.get("custom"),
    )
    setup_middleware(app, config)
    app.include_router(router)
    return app


__all__ = ["create_app"]
