
from app.storage.models import (
    Base,
    SEOProject,
    WorkflowRun,
    AgentExecution,
    TokenUsage,
)


def main():
    print("Registered database tables:")

    for table_name in Base.metadata.tables:
        print(f"- {table_name}")

    print("\nModel classes imported successfully.")

    project = SEOProject(
        name="Test SEO Project",
        website_url="https://example.com",
    )

    print(f"\nTest project: {project}")


if __name__ == "__main__":
    main()