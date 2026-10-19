from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field, model_validator

DEMO_MAX_PAGES = 15


def _csv(name: str, default: str) -> list[str]:
    return [
        item.strip().rstrip("/")
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


class WebSettings(BaseModel):
    environment: str = "development"
    frontend_origins: list[str] = Field(default_factory=list)
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    rate_limit_salt: str | None = None
    demo_max_pages: int = Field(default=DEMO_MAX_PAGES, ge=1, le=DEMO_MAX_PAGES)
    demo_retention_hours: int = Field(default=24, ge=1, le=168)
    demo_rate_limit_per_hour: int = Field(default=3, ge=1, le=20)
    demo_timeout_seconds: int = Field(default=180, ge=30, le=240)
    demo_request_timeout_seconds: float = Field(default=12, ge=3, le=30)
    supabase_report_bucket: str = "seo-demo-reports"

    @model_validator(mode="after")
    def validate_supabase_configuration(self) -> WebSettings:
        configured = [self.supabase_url, self.supabase_secret_key, self.rate_limit_salt]
        if any(configured) and not all(configured):
            raise ValueError(
                "SUPABASE_URL, SUPABASE_SECRET_KEY, and RATE_LIMIT_SALT must be configured together."
            )
        if self.environment == "production" and not all(configured):
            raise ValueError(
                "Production requires SUPABASE_URL, SUPABASE_SECRET_KEY, and RATE_LIMIT_SALT."
            )
        return self

    @property
    def uses_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @classmethod
    def from_environment(cls) -> WebSettings:
        return cls(
            environment=os.getenv(
                "APP_ENV",
                "production" if os.getenv("VERCEL") else "development",
            )
            .strip()
            .lower(),
            frontend_origins=_csv(
                "FRONTEND_ORIGINS",
                "http://localhost:5173,https://huzaifa-170504.github.io",
            ),
            supabase_url=os.getenv("SUPABASE_URL") or None,
            supabase_secret_key=os.getenv("SUPABASE_SECRET_KEY") or None,
            rate_limit_salt=os.getenv("RATE_LIMIT_SALT") or None,
            demo_max_pages=int(os.getenv("DEMO_MAX_PAGES", str(DEMO_MAX_PAGES))),
            demo_retention_hours=int(os.getenv("DEMO_RETENTION_HOURS", "24")),
            demo_rate_limit_per_hour=int(os.getenv("DEMO_RATE_LIMIT_PER_HOUR", "3")),
            demo_timeout_seconds=int(os.getenv("DEMO_TIMEOUT_SECONDS", "180")),
            demo_request_timeout_seconds=float(
                os.getenv("DEMO_REQUEST_TIMEOUT_SECONDS", "12")
            ),
            supabase_report_bucket=os.getenv(
                "SUPABASE_REPORT_BUCKET", "seo-demo-reports"
            ),
        )


@lru_cache(maxsize=1)
def get_web_settings() -> WebSettings:
    return WebSettings.from_environment()
