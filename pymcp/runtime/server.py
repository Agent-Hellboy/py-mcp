"""FastAPI app factory for the layered runtime."""

from __future__ import annotations

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
from ..session.store import SessionManager
from ..settings import ServerSettings


def create_app(
    middleware_config: Optional[MiddlewareConfig] = None,
    server_settings: Optional[ServerSettings] = None,
    **kwargs,
):
    app = FastAPI(title="PyMCP Kit", summary="Composable MCP toolkit on FastAPI")
    server_kwargs = {}
    if kwargs.get("server_name") is not None:
        server_kwargs["name"] = kwargs["server_name"]
    if kwargs.get("server_version") is not None:
        server_kwargs["version"] = kwargs["server_version"]
    app.state.server_settings = server_settings or ServerSettings(**server_kwargs)
    app.state.roots = list(kwargs.get("roots", []))
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
    )
    setup_middleware(app, config)
    app.include_router(router)
    attach_tool_list_changed_notifications(app)
    attach_prompt_list_changed_notifications(app)
    attach_resource_list_changed_notifications(app)
    attach_resource_updated_notifications(app)
    return app


__all__ = ["create_app"]
