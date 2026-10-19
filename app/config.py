from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _optional_integer(name: str, minimum: int, maximum: int) -> int | None:
    """Read an optional bounded integer; an unset value means no limit."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


class ModelConfig(BaseModel):
    provider: str
    model_name: str
    temperature: float = Field(ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float = Field(gt=0, le=1800)


class RuntimeConfig(BaseModel):
    max_revisions: int = Field(default=3, ge=0, le=10)
    max_technical_retries: int = Field(default=2, ge=0, le=5)
    # Full-site crawls are the default. Deployments can still impose an explicit
    # operational ceiling with MAX_AUDIT_PAGES when required.
    max_audit_pages: int | None = Field(default=None, ge=1, le=1_000_000)
    max_competitor_pages: int = Field(default=20, ge=1, le=100)
    http_timeout_seconds: float = Field(default=15, gt=0, le=120)
    article_approval_score: float = Field(default=80, ge=0, le=100)
    seo_title_max_characters: int = Field(default=60, ge=30, le=100)
    meta_description_max_characters: int = Field(default=160, ge=80, le=300)
    allow_private_urls: bool = False

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        return cls(
            max_revisions=_integer("MAX_CONTENT_REVISIONS", 3, 0, 10),
            max_technical_retries=_integer("MAX_TECHNICAL_RETRIES", 2, 0, 5),
            max_audit_pages=_optional_integer("MAX_AUDIT_PAGES", 1, 1_000_000),
            max_competitor_pages=_integer("MAX_COMPETITOR_PAGES", 20, 1, 100),
            http_timeout_seconds=_float("HTTP_TIMEOUT_SECONDS", 15, 1, 120),
            article_approval_score=_float("ARTICLE_APPROVAL_SCORE", 80, 0, 100),
            seo_title_max_characters=_integer("SEO_TITLE_MAX_CHARACTERS", 60, 30, 100),
            meta_description_max_characters=_integer(
                "META_DESCRIPTION_MAX_CHARACTERS", 160, 80, 300
            ),
            allow_private_urls=os.getenv("ALLOW_PRIVATE_URLS", "false").lower()
            in {"1", "true", "yes"},
        )


@lru_cache(maxsize=1)
def get_runtime_config() -> RuntimeConfig:
    return RuntimeConfig.from_environment()
