# Security

`pymcp-kit` ships optional authentication and authorization hooks. They are off by default and are activated through `create_app(...)` or `MiddlewareConfig(...)`.

## Bearer Token Authentication

`TokenMapAuthenticator` maps static Bearer tokens to `Principal` objects:

```python
from pymcp import create_app
from pymcp.security import TokenMapAuthenticator


app = create_app(
    authn=TokenMapAuthenticator(
        {
            "secret-token": {
                "subject": "alice",
                "display_name": "Alice",
                "roles": ["ops"],
                "scopes": ["tools:*", "tasks:*"],
                "claims": {"tenant": "acme"},
            }
        }
    ),
    require_authn=True,
)
```

With `require_authn=True`, unauthenticated requests receive `401`.

## Rule-Based Authorization

`RuleBasedAuthorizer` evaluates ordered allow/deny rules:

```python
from pymcp import create_app
from pymcp.security import RuleBasedAuthorizer, TokenMapAuthenticator


authn = TokenMapAuthenticator(
    {
        "secret-token": {
            "subject": "alice",
            "roles": ["ops"],
            "scopes": ["tools:*", "tasks:*"],
        }
    }
)

authz = RuleBasedAuthorizer(
    {
        "default_effect": "deny",
        "hide_unauthorized_capabilities": True,
        "hide_unauthorized_tools": True,
        "rules": [
            {
                "methods": ["initialize", "ping", "tools/list", "tasks/list", "tasks/get", "tasks/result"],
                "allow_subjects": ["alice"],
                "effect": "allow",
            },
            {
                "methods": ["tools/call"],
                "tool": "deploy_*",
                "allow_roles": ["ops"],
                "effect": "allow",
            },
        ],
    }
)

app = create_app(
    authn=authn,
    authz=authz,
    require_authn=True,
)
```

## Loading Authz Rules From JSON

```python
from pymcp.security import RuleBasedAuthorizer, load_json_config


authz = RuleBasedAuthorizer(load_json_config("authz_policy.json"))
```

## Useful Knobs

- `hide_unauthorized_capabilities`: remove disallowed capability fragments from `initialize`
- `hide_unauthorized_tools`: filter `tools/list` output to only visible tools
- `auth_exempt_paths`: skip auth middleware on selected HTTP routes

## Task Visibility Under Auth

When authentication is enabled, task ownership follows the authenticated principal rather than the raw session ID. That matters for `tasks/list`, `tasks/get`, `tasks/cancel`, and `tasks/result`.

## Practical Layout

- keep token maps or authn setup in `config.py`
- keep JSON authz policies in a separate file
- pass `authn`, `authz`, and `require_authn` into `create_app()`
- use capability and tool filtering if clients should not even discover restricted functionality
