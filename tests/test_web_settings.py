from __future__ import annotations

import pytest

from app.web.settings import WebSettings


def test_web_settings_require_complete_supabase_secret_configuration() -> None:
    with pytest.raises(ValueError, match="must be configured together"):
        WebSettings(supabase_url="https://example.supabase.co")


def test_public_demo_cannot_exceed_fifteen_pages() -> None:
    with pytest.raises(ValueError):
        WebSettings(demo_max_pages=16)


def test_production_requires_durable_supabase_configuration() -> None:
    with pytest.raises(ValueError, match="Production requires"):
        WebSettings(environment="production")
