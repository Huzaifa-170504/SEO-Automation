
from app.workflow.state import WorkflowState


def main():
    state = WorkflowState(
        project_id=1,
        website_url="https://example.com",
        project_name="Test SEO Project",
    )

    state.mark_started()
    state.add_result("website_auditor", {"score": 85})
    state.add_error("content_strategist", "Test error")

    print("Workflow state initialized.")
    print("Status:", state.status)
    print("Website:", state.website_url)
    print("Results:", state.results)
    print("Errors:", state.errors)

    state.mark_completed()
    print("Final status:", state.status)
    print("Completed at:", state.completed_at)


if __name__ == "__main__":
    main()
