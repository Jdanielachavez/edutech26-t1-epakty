"""Vercel serverless entry point — exports the FastAPI ASGI app.

Vercel's Python runtime discovers `app` and mounts it at /api/*.
Every route in the FastAPI app becomes /api/v1/... via the rewrite in vercel.json.

Required env vars on Vercel:
  DATABASE_URL          — Supabase pooler connection string (Transaction mode, port 6543)
  PAKTAI_AUTH_TOKENS    — JSON: {"<token>": {"role": "<role>"}, ...}
  EPAKTI_ENGINE_BASE_URL — engine stub or production motor URL
  EPAKTI_ENGINE_API_KEY  — key for engine auth
  ENVIRONMENT           — 'staging' or 'production'
  CORS_ORIGINS          — comma-separated allowed origins
  PAKTAI_USERS          — JSON de usuarios con hash scrypt (python -m scripts.create_user)
  SESSION_SECRET        — 32+ caracteres para firmar sesiones de inicio de sesión
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('ENVIRONMENT', 'staging')

from backend.production.api import create_app

app = create_app()
