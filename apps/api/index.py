"""Vercel entrypoint: the ASGI app lives in app/asgi.py."""

from app.asgi import app

__all__ = ["app"]
