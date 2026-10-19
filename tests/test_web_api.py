from __future__ import annotations

from typing import Any, ClassVar

from fastapi.testclient import TestClient

import app.web.service as service_module
from app.web.api import create_app
from app.web.repository import MemoryAuditRepository
from app.web.settings import WebSettings


class FakeAuditor:
    instances: ClassVar[list[FakeAuditor]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.options = kwargs
        self.instances.append(self)

    async def audit(self, website_url: str) -> dict[str, Any]:
        return {
            "website": website_url,
            "pages_discovered": 2,
            "pages_crawled": 1,
            "pages_failed": 0,
            "max_pages": self.options["max_pages"],
            "crawl_limit_reached": True,
            "errors": [],
            "pages": [
                {
                    "url": website_url,
                    "status_code": 200,
                    "title": "Example",
                    "meta_description": "",
                    "h1_headings": ["Example"],
                    "canonical": website_url,
                    "image_count": 0,
                    "internal_link_count": 1,
                    "external_link_count": 0,
                    "word_count": 12,
                    "language": "en",
                    "issues": ["Missing meta description"],
                }
            ],
        }


def settings(**overrides: Any) -> WebSettings:
    values: dict[str, Any] = {
        "frontend_origins": ["https://huzaifa-170504.github.io"],
        "demo_max_pages": 15,
        "demo_rate_limit_per_hour": 3,
    }
    values.update(overrides)
    return WebSettings(**values)


def test_health_and_sample_are_available_without_credentials() -> None:
    app = create_app(settings(), MemoryAuditRepository())
    with TestClient(app) as client:
        health = client.get("/api/health")
        sample = client.get("/api/v1/sample")

    assert health.status_code == 200
    assert health.json()["demo_max_pages"] == 15
    assert health.json()["persistence"] == "memory"
    assert sample.status_code == 200
    assert sample.json()["summary"]["issue_count"] == 5


def test_live_audit_is_capped_and_protected_by_opaque_token(monkeypatch) -> None:
    FakeAuditor.instances.clear()
    monkeypatch.setattr(service_module, "WebsiteAuditor", FakeAuditor)
    app = create_app(settings(), MemoryAuditRepository())

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/audits",
            json={"website_url": "https://example.com", "company": ""},
            headers={"x-forwarded-for": "203.0.113.8"},
        )
        body = created.json()
        audit_id = body["audit_id"]
        token = body["access_token"]
        forbidden = client.get(
            f"/api/v1/audits/{audit_id}", headers={"X-Audit-Token": "x" * 32}
        )
        fetched = client.get(
            f"/api/v1/audits/{audit_id}", headers={"X-Audit-Token": token}
        )
        report = client.get(
            f"/api/v1/audits/{audit_id}/report", headers={"X-Audit-Token": token}
        )

    assert created.status_code == 201
    assert FakeAuditor.instances[0].options["max_pages"] == 15
    assert body["summary"]["issue_count"] == 1
    assert body["summary"]["crawl_limit_reached"] is True
    assert forbidden.status_code == 404
    assert fetched.status_code == 200
    assert fetched.json()["access_token"] is None
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")


def test_rate_limit_rejects_repeated_public_demo_requests(monkeypatch) -> None:
    monkeypatch.setattr(service_module, "WebsiteAuditor", FakeAuditor)
    app = create_app(
        settings(demo_rate_limit_per_hour=1),
        MemoryAuditRepository(),
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/audits",
            json={"website_url": "example.com"},
            headers={"x-forwarded-for": "198.51.100.9"},
        )
        second = client.post(
            "/api/v1/audits",
            json={"website_url": "example.com"},
            headers={"x-forwarded-for": "198.51.100.9"},
        )

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.headers["retry-after"] == "3600"


def test_honeypot_rejects_automated_submission() -> None:
    app = create_app(settings(), MemoryAuditRepository())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/audits",
            json={"website_url": "example.com", "company": "bot"},
        )

    assert response.status_code == 422
