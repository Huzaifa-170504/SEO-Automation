class SEOAutomationError(RuntimeError):
    """Base exception for expected workflow failures."""


class AgentExecutionError(SEOAutomationError):
    pass


class CrawlerError(SEOAutomationError):
    pass


class ModelProviderError(SEOAutomationError):
    pass


class StructuredOutputError(ModelProviderError):
    pass


class WorkflowError(SEOAutomationError):
    pass


class ReviewLimitReached(WorkflowError):
    pass
