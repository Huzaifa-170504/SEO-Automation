
from app.workflow.cost_controller import CostController


def main():
    controller = CostController()

    # Example pricing for testing only, not actual API rates.
    controller.set_pricing(
        model_name="test-model",
        input_per_million="1.00",
        output_per_million="2.00",
    )

    controller.record_usage(
        provider="test",
        model_name="test-model",
        input_tokens=1000,
        output_tokens=500,
    )

    controller.record_usage(
        provider="ollama",
        model_name="qwen-seo:4b",
        input_tokens=2000,
        output_tokens=1000,
    )

    print("Cost controller initialized.")
    print("Summary:", controller.summary())

    assert controller.total_input_tokens == 3000
    assert controller.total_output_tokens == 1500
    assert controller.total_tokens == 4500
    assert str(controller.total_cost_usd) == "0.002"

    print("All cost controller tests passed.")


if __name__ == "__main__":
    main()