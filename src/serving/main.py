"""Legacy ASGI entrypoint; explicit-storage callers import app_factory instead."""
from .app_factory import create_app


app = create_app()
