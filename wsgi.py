"""Point d'entree WSGI pour PythonAnywhere / gunicorn.

Sur PythonAnywhere : creez une application web "Manual configuration"
et pointez le fichier WSGI sur ce module.
"""

import os

os.environ.setdefault("FILMHUB_HOSTED", "1")
os.environ.setdefault("FILMHUB_DLNA", "0")
os.environ.setdefault("FILMHUB_PUBLIC", "1")

from backend.main import app  # noqa: E402

application = app