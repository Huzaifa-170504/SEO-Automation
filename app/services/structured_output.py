from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.exceptions import StructuredOutputError

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_structured_output(text: str, model: type[ModelT]) -> ModelT:
    """Parse direct or fenced JSON once and validate it against a schema."""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    errors: list[str] = []
    for candidate in dict.fromkeys(candidates):
        try:
            return model.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(str(exc))
    raise StructuredOutputError("Structured model output was invalid: " + errors[-1][:500])


async def parse_with_one_repair(
    text: str,
    model: type[ModelT],
    repair: Callable[[str, str], Awaitable[str]],
) -> ModelT:
    """Try normal recovery, then exactly one schema-correction request."""
    try:
        return parse_structured_output(text, model)
    except StructuredOutputError:
        repaired = await repair(text, model.model_json_schema().__str__())
        try:
            return parse_structured_output(repaired, model)
        except StructuredOutputError as final_error:
            raise StructuredOutputError(
                "Structured output remained invalid after one correction attempt."
            ) from final_error
