"""
WSGI config for SIG project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
from pathlib import Path

try:
	from dotenv import load_dotenv

	BASE_DIR = Path(__file__).resolve().parent.parent
	env_path = BASE_DIR / ".env"
	if env_path.exists():
		load_dotenv(env_path, override=False)
except Exception:
	pass

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIG.settings')

application = get_wsgi_application()
