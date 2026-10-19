"""
Local Qwen model client using the Ollama HTTP API.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any, Self

import httpx
from dotenv import load_dotenv

load_dotenv()


class QwenClient:
    """Asynchronous client for a locally running Ollama model."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "OLLAMA_BASE_URL",
                "http://127.0.0.1:11434",
            )
        ).rstrip("/")

        self.model = model or os.getenv(
            "QWEN_MODEL",
            "qwen-seo:4b",
        )

        self.timeout = timeout or float(os.getenv("QWEN_TIMEOUT_SECONDS", "600"))
        self.last_usage: dict[str, Any] = {}

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> str:
        """Generate a response from the local Qwen model."""
        messages: list[dict[str, Any]] = []

        if system:
            messages.append(
                {
                    "role": "system",
                    "content": system,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        options: dict[str, float | int] = {
            "temperature": temperature,
            "num_predict": int(os.getenv("QWEN_MAX_OUTPUT_TOKENS", "4096")),
            "num_ctx": int(os.getenv("QWEN_CONTEXT_TOKENS", "32768")),
        }
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": options,
        }

        response = await self.client.post(
            "/api/chat",
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        content = data.get("message", {}).get("content", "")

        if not content:
            raise RuntimeError("Qwen returned an empty response.")

        input_tokens = int(data.get("prompt_eval_count") or 0)
        output_tokens = int(data.get("eval_count") or 0)
        self.last_usage = {
            "provider": "qwen",
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

        return content

    async def health_check(self) -> bool:
        """Check whether the Ollama server is reachable."""
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()


if __name__ == "__main__":
    print("Qwen client module loaded.")
