"""FastAPI app factory for the layered runtime."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from ..middleware import MiddlewareConfig, setup_middleware
from ..registries.registry import (
    RegistryManager,
    prompt_registry,
    resource_registry,
    tool_registry,
)
from ..server import router
from ..session.notifications import (
    attach_prompt_list_changed_notifications,
    attach_resource_list_changed_notifications,
    attach_resource_updated_notifications,
    attach_tool_list_changed_notifications,
)
from ..session.store import SessionManager, get_session_manager
from ..settings import ServerSettings
from ..transport.shutdown import ensure_shutdown_event


@asynccontextmanager
async def _mcp_lifespan(app: FastAPI):
    ensure_shutdown_event(app)
    yield
    ensure_shutdown_event(app).set()
    await get_session_manager(app).shutdown()


def create_app(
    middleware_config: Optional[MiddlewareConfig] = None,
    server_settings: Optional[ServerSettings] = None,
    **kwargs,
):
    app = FastAPI(
        title="PyMCP Kit",
        summary="Composable MCP toolkit on FastAPI",
        lifespan=_mcp_lifespan,
    )
    server_kwargs = {}
    if kwargs.get("server_name") is not None:
        server_kwargs["name"] = kwargs["server_name"]
    if kwargs.get("server_version") is not None:
        server_kwargs["version"] = kwargs["server_version"]
    if kwargs.get("server_title") is not None:
        server_kwargs["title"] = kwargs["server_title"]
    if kwargs.get("server_description") is not None:
        server_kwargs["description"] = kwargs["server_description"]
    if kwargs.get("server_website_url") is not None:
        server_kwargs["website_url"] = kwargs["server_website_url"]
    if kwargs.get("server_icons") is not None:
        server_kwargs["icons"] = kwargs["server_icons"]
    app.state.server_settings = server_settings or ServerSettings(**server_kwargs)
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
        authn=kwargs.get("authn"),
        authz=kwargs.get("authz"),
        require_authn=kwargs.get("require_authn", False),
        auth_exempt_paths=kwargs.get("auth_exempt_paths"),
        oauth=kwargs.get("oauth"),
    )
    setup_middleware(app, config)
    app.include_router(router)
    attach_tool_list_changed_notifications(app)
    attach_prompt_list_changed_notifications(app)
    attach_resource_list_changed_notifications(app)
    attach_resource_updated_notifications(app)
    return app


__all__ = ["create_app"]
