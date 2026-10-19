
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ModelPricing:
    """Price per million tokens, in USD."""

    input_per_million: Decimal = Decimal("0")
    output_per_million: Decimal = Decimal("0")


@dataclass
class UsageRecord:
    """Token usage for one model request."""

    provider: str
    model_name: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


@dataclass
class CostController:
    """Track token usage and estimated model costs."""

    pricing: dict[str, ModelPricing] = field(default_factory=dict)
    records: list[UsageRecord] = field(default_factory=list)

    def set_pricing(
        self,
        model_name: str,
        input_per_million: Decimal | str | float,
        output_per_million: Decimal | str | float,
    ) -> None:
        """Configure model pricing per million tokens."""
        self.pricing[model_name] = ModelPricing(
            input_per_million=Decimal(str(input_per_million)),
            output_per_million=Decimal(str(output_per_million)),
        )

    def record_usage(
        self,
        provider: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """Record usage and calculate estimated cost."""

        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative.")

        rates = self.pricing.get(model_name, ModelPricing())

        cost = (
            Decimal(input_tokens)
            * rates.input_per_million
            + Decimal(output_tokens)
            * rates.output_per_million
        ) / Decimal("1000000")

        record = UsageRecord(
            provider=provider,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

        self.records.append(record)
        return record

    @property
    def total_input_tokens(self) -> int:
        return sum(record.input_tokens for record in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(record.output_tokens for record in self.records)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost_usd(self) -> Decimal:
        return sum(
            (record.estimated_cost_usd for record in self.records),
            Decimal("0"),
        )

    def summary(self) -> dict:
        """Return a summary of tracked usage and cost."""
        return {
            "requests": len(self.records),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": str(self.total_cost_usd),
        }

    def reset(self) -> None:
        """Clear all recorded usage."""
        self.records.clear()