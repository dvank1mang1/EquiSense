"""Optional research extension layer for ranking/regression experiments."""

from app.research_models.runner import (
    ResearchConfig,
    ResearchRunResult,
    run_research_experiment,
)

__all__ = [
    "ResearchConfig",
    "ResearchRunResult",
    "run_research_experiment",
]
