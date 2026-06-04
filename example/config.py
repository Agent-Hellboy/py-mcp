from pymcp.middleware import MiddlewareConfig
from pymcp.security import OAuthProtectedResourceConfig

middleware_config = MiddlewareConfig(
    cors={
        "allow_origins": ["https://myapp.com"],
        "allow_methods": ["GET", "POST"],
        "allow_headers": ["*"],
        "allow_credentials": True,
    },
    logging={
        "level": "DEBUG",
        "format": "%(asctime)s %(levelname)s %(message)s",
    },
    compression={"enabled": True},
    oauth=OAuthProtectedResourceConfig(
        authorization_servers=["https://auth.example.com"],
        scopes_supported=["mcp:access"],
        resource_name="Example MCP",
    ),
    custom=[
        # Add custom middleware classes here if needed
    ],
)
