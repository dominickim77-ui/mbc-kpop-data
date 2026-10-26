"""Fail closed on cloud configuration and unsupported filesystem writers."""
import os
from fastapi import HTTPException
from security.analysis_origin import configured_origin


def cloud():
    return os.environ.get("VERCEL") == "1"


def validate():
    if not cloud():
        return
    if os.environ.get("VERCEL_ENV") not in {"preview", "production"}:
        raise RuntimeError("Unsupported Vercel environment")
    if os.environ.get("KPOP_PREVIEW_SYNTHETIC") != "1":
        raise RuntimeError("Cloud deployments must use the isolated synthetic dataset")
    if not configured_origin():
        raise RuntimeError("Vercel requires an exact HTTPS project origin")
    if os.environ.get("KPOP_DB_BACKEND", "").strip().lower() != "postgresql":
        raise RuntimeError("Vercel requires durable PostgreSQL storage")
    try:
        from psycopg.conninfo import conninfo_to_dict
        config = conninfo_to_dict(os.environ.get("KPOP_POSTGRES_DSN", ""))
    except Exception:
        raise RuntimeError("PostgreSQL configuration is unavailable") from None
    if config.get("sslmode") != "verify-full":
        raise RuntimeError("PostgreSQL requires verify-full TLS")
    if config.get("user", "").split(".")[0] != "kpop_class_app":
        raise RuntimeError("Vercel requires the restricted application role")
    if os.environ.get("KPOP_POSTGRES_SCHEMA") != "kpop_class_preview":
        raise RuntimeError("Vercel requires the isolated application schema")
    pem = os.environ.get("KPOP_POSTGRES_SSLROOTCERT_PEM", "")
    if "-----BEGIN CERTIFICATE-----" not in pem or "PRIVATE KEY" in pem or len(pem) > 32768:
        raise RuntimeError("The public PostgreSQL TLS root certificate is required")


def require_supported_write():
    from security.preview_data import synthetic
    if cloud() or synthetic():
        raise HTTPException(503, "Preview에서는 외부 API 수집·유료 생성이 꺼져 있습니다.")
