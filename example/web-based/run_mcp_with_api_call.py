import requests

from pymcp import create_app
from pymcp.registry import tool_registry


@tool_registry.register
def callFlaskHelloTool() -> str:
    """Calls the /hello endpoint of the Flask API server running on port 5005 and returns the message."""
    try:
        resp = requests.get("http://127.0.0.1:5005/hello", timeout=2)
        resp.raise_for_status()
        data = resp.json()
        return f"Flask API says: {data.get('message', 'No message')}"
    except Exception as e:
        return f"Error calling Flask API: {e}"


if __name__ == "__main__":
    import uvicorn

    print(
        "[INFO] Make sure to start the Flask API server (flask_api_server.py) before running this example."
    )
    uvicorn.run(create_app(middleware_config=None), host="0.0.0.0", port=8088)
