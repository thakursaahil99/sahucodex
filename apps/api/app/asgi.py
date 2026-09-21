"""ASGI entrypoint: `uvicorn app.asgi:app`. Settings come from the environment."""

from app.main import create_app

app = create_app()
