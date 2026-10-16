"""Vercel discovers this Flask application; desktop bundles remain separate."""
from server.hosted import create_app

app = create_app()
