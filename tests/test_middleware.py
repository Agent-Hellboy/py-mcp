import logging

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.middleware import MiddlewareConfig


class CustomHeaderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-custom-middleware"] = b"true"
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)


def test_gzip_and_custom_middleware():
    config = MiddlewareConfig(
        compression={"enabled": True},
        custom=[CustomHeaderMiddleware],
    )
    app = create_app(middleware_config=config)

    @app.get("/plain")
    def plain():
        return PlainTextResponse("Hello World!" * 100)

    client = TestClient(app)
    response = client.get("/plain", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.headers.get("x-custom-middleware") == "true"


def test_create_app_applies_middleware_logging_level():
    config = MiddlewareConfig(
        logging={
            "level": "DEBUG",
            "format": "%(asctime)s %(levelname)s %(message)s",
        }
    )
    create_app(middleware_config=config)

    assert logging.getLogger("pymcp").getEffectiveLevel() == logging.DEBUG
