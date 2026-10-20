from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx

from app.web.models import DemoAuditResult, DemoContentResult


class AuditNotFoundError(LookupError):
    """Raised when an audit is absent, expired, or accessed with the wrong token."""


class RateLimitExceededError(RuntimeError):
    """Raised when a client exceeds the configured demo allowance."""


class ContentNotFoundError(LookupError):
    """Raised when generated content is absent, expired, or unauthorized."""


class AuditRepository(Protocol):
    async def enforce_rate_limit(
        self, client_hash: str, *, limit: int, window: timedelta
    ) -> None: ...

    async def save(
        self,
        result: DemoAuditResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None: ...

    async def get(
        self, audit_id: UUID, *, access_token_hash: str
    ) -> DemoAuditResult: ...

    async def get_pdf(self, audit_id: UUID, *, access_token_hash: str) -> bytes: ...

    async def save_content(
        self,
        result: DemoContentResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None: ...

    async def get_content(
        self, content_id: UUID, *, access_token_hash: str
    ) -> DemoContentResult: ...

    async def get_content_pdf(
        self, content_id: UUID, *, access_token_hash: str
    ) -> bytes: ...

    async def close(self) -> None: ...


class MemoryAuditRepository:
    """Process-local persistence used only for development and automated tests."""

    def __init__(self) -> None:
        self._audits: dict[UUID, tuple[DemoAuditResult, str, bytes]] = {}
        self._content: dict[UUID, tuple[DemoContentResult, str, bytes]] = {}
        self._requests: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def enforce_rate_limit(
        self, client_hash: str, *, limit: int, window: timedelta
    ) -> None:
        now = datetime.now(UTC)
        cutoff = now - window
        async with self._lock:
            requests = self._requests[client_hash]
            while requests and requests[0] < cutoff:
                requests.popleft()
            if len(requests) >= limit:
                raise RateLimitExceededError
            requests.append(now)

    async def save(
        self,
        result: DemoAuditResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None:
        stored = result.model_copy(update={"access_token": None}, deep=True)
        async with self._lock:
            self._audits[result.audit_id] = (stored, access_token_hash, pdf_bytes)

    async def get(self, audit_id: UUID, *, access_token_hash: str) -> DemoAuditResult:
        async with self._lock:
            record = self._audits.get(audit_id)
        if record is None:
            raise AuditNotFoundError
        result, expected_hash, _ = record
        if expected_hash != access_token_hash or result.expires_at <= datetime.now(
            UTC
        ):
            raise AuditNotFoundError
        return result.model_copy(deep=True)

    async def get_pdf(self, audit_id: UUID, *, access_token_hash: str) -> bytes:
        await self.get(audit_id, access_token_hash=access_token_hash)
        return self._audits[audit_id][2]

    async def save_content(
        self,
        result: DemoContentResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None:
        stored = result.model_copy(update={"access_token": None}, deep=True)
        async with self._lock:
            self._content[result.content_id] = (stored, access_token_hash, pdf_bytes)

    async def get_content(
        self, content_id: UUID, *, access_token_hash: str
    ) -> DemoContentResult:
        async with self._lock:
            record = self._content.get(content_id)
        if record is None:
            raise ContentNotFoundError
        result, expected_hash, _ = record
        if expected_hash != access_token_hash or result.expires_at <= datetime.now(UTC):
            raise ContentNotFoundError
        return result.model_copy(deep=True)

    async def get_content_pdf(
        self, content_id: UUID, *, access_token_hash: str
    ) -> bytes:
        await self.get_content(content_id, access_token_hash=access_token_hash)
        return self._content[content_id][2]

    async def close(self) -> None:
        return None


class SupabaseAuditRepository:
    """Backend-only Supabase REST and Storage adapter."""

    def __init__(self, url: str, secret_key: str, bucket: str) -> None:
        self._url = url.rstrip("/")
        self._bucket = bucket
        self._client = httpx.AsyncClient(
            timeout=20,
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
            },
        )

    async def enforce_rate_limit(
        self, client_hash: str, *, limit: int, window: timedelta
    ) -> None:
        response = await self._client.post(
            f"{self._url}/rest/v1/rpc/consume_demo_audit_quota",
            json={
                "p_client_hash": client_hash,
                "p_limit": limit,
                "p_window_seconds": int(window.total_seconds()),
            },
        )
        response.raise_for_status()
        if response.json() is not True:
            raise RateLimitExceededError

    async def save(
        self,
        result: DemoAuditResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None:
        object_path = f"{result.audit_id}.pdf"
        upload = await self._client.post(
            f"{self._url}/storage/v1/object/{self._bucket}/{object_path}",
            headers={"Content-Type": "application/pdf", "x-upsert": "false"},
            content=pdf_bytes,
        )
        upload.raise_for_status()
        try:
            response = await self._client.post(
                f"{self._url}/rest/v1/demo_audits",
                headers={"Prefer": "return=minimal"},
                json={
                    "id": str(result.audit_id),
                    "website_url": result.website_url,
                    "share_token_hash": access_token_hash,
                    "status": result.status,
                    "pages_discovered": result.summary.pages_discovered,
                    "pages_crawled": result.summary.pages_crawled,
                    "pages_failed": result.summary.pages_failed,
                    "issue_count": result.summary.issue_count,
                    "report": result.model_copy(
                        update={"access_token": None}
                    ).model_dump(mode="json"),
                    "report_object_path": object_path,
                    "created_at": result.created_at.isoformat(),
                    "expires_at": result.expires_at.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            await self._client.request(
                "DELETE",
                f"{self._url}/storage/v1/object/{self._bucket}",
                json={"prefixes": [object_path]},
            )
            raise

    async def get(self, audit_id: UUID, *, access_token_hash: str) -> DemoAuditResult:
        response = await self._client.get(
            f"{self._url}/rest/v1/demo_audits",
            params={
                "id": f"eq.{audit_id}",
                "share_token_hash": f"eq.{access_token_hash}",
                "expires_at": f"gt.{datetime.now(UTC).isoformat()}",
                "select": "report",
                "limit": "1",
            },
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise AuditNotFoundError
        return DemoAuditResult.model_validate(rows[0]["report"])

    async def get_pdf(self, audit_id: UUID, *, access_token_hash: str) -> bytes:
        await self.get(audit_id, access_token_hash=access_token_hash)
        response = await self._client.get(
            f"{self._url}/storage/v1/object/{self._bucket}/{audit_id}.pdf"
        )
        if response.status_code == 404:
            raise AuditNotFoundError
        response.raise_for_status()
        return response.content

    async def save_content(
        self,
        result: DemoContentResult,
        *,
        access_token_hash: str,
        pdf_bytes: bytes,
    ) -> None:
        object_path = f"content/{result.content_id}.pdf"
        upload = await self._client.post(
            f"{self._url}/storage/v1/object/{self._bucket}/{object_path}",
            headers={"Content-Type": "application/pdf", "x-upsert": "false"},
            content=pdf_bytes,
        )
        upload.raise_for_status()
        try:
            response = await self._client.post(
                f"{self._url}/rest/v1/demo_content_jobs",
                headers={"Prefer": "return=minimal"},
                json={
                    "id": str(result.content_id),
                    "audit_id": str(result.audit_id),
                    "share_token_hash": access_token_hash,
                    "status": result.status,
                    "primary_keyword": result.primary_keyword,
                    "result": result.model_copy(
                        update={"access_token": None}
                    ).model_dump(mode="json"),
                    "report_object_path": object_path,
                    "created_at": result.created_at.isoformat(),
                    "expires_at": result.expires_at.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            await self._client.request(
                "DELETE",
                f"{self._url}/storage/v1/object/{self._bucket}",
                json={"prefixes": [object_path]},
            )
            raise

    async def get_content(
        self, content_id: UUID, *, access_token_hash: str
    ) -> DemoContentResult:
        response = await self._client.get(
            f"{self._url}/rest/v1/demo_content_jobs",
            params={
                "id": f"eq.{content_id}",
                "share_token_hash": f"eq.{access_token_hash}",
                "expires_at": f"gt.{datetime.now(UTC).isoformat()}",
                "select": "result",
                "limit": "1",
            },
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise ContentNotFoundError
        return DemoContentResult.model_validate(rows[0]["result"])

    async def get_content_pdf(
        self, content_id: UUID, *, access_token_hash: str
    ) -> bytes:
        result = await self.get_content(
            content_id, access_token_hash=access_token_hash
        )
        response = await self._client.get(
            f"{self._url}/storage/v1/object/{self._bucket}/content/{result.content_id}.pdf"
        )
        if response.status_code == 404:
            raise ContentNotFoundError
        response.raise_for_status()
        return response.content

    async def close(self) -> None:
        await self._client.aclose()
