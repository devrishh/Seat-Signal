"""Entry point for Vercel and other hosts: they look for `app` in index.py.
The app itself is in backend/app.py."""
from backend.app import app  # noqa: F401
