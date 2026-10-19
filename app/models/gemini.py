"""
Asynchronous Gemini API client for SEO-AUTOMATION.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class GeminiClient:
    """Asynchronous client for Google's Gemini API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is missing. Add it to your .env file.")

        self.model = model or os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        )

        self.timeout = timeout

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000),
            ),
        )

        self.last_usage: dict[str, Any] = {}

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> str:
        """Generate a text response and record token usage."""
        config: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
        }
        if top_p is not None:
            config["top_p"] = top_p
        if top_k is not None:
            config["top_k"] = top_k

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(**config),
        )

        usage = response.usage_metadata

        self.last_usage = {
            "provider": "gemini",
            "model": self.model,
            "input_tokens": (
                getattr(
                    usage,
                    "prompt_token_count",
                    0,
                )
                or 0
                if usage
                else 0
            ),
            "output_tokens": (
                getattr(
                    usage,
                    "candidates_token_count",
                    0,
                )
                or 0
                if usage
                else 0
            ),
            "total_tokens": (
                getattr(
                    usage,
                    "total_token_count",
                    0,
                )
                or 0
                if usage
                else 0
            ),
        }

        content = response.text

        if not content:
            raise RuntimeError("Gemini returned an empty response.")

        return content

    async def close(self) -> None:
        """Close the asynchronous Gemini client."""
        await self.client.aio.aclose()

    async def __aenter__(self) -> GeminiClient:
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.close()


if __name__ == "__main__":
    print("Gemini client module loaded.")
