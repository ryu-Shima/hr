"\"\"\"Dependency injection container for the screening system.\"\"\""

from __future__ import annotations

from dependency_injector import containers, providers

from .adapters import BizReachAdapter
from .core import JDMatcher, SalaryEvaluator, ScreeningCore, TenureEvaluator
from .pipeline import AdapterRegistry, ScreeningPipeline


class ScreeningContainer(containers.DeclarativeContainer):
    """Dependency-injector container definition."""

    config = providers.Configuration()

    bizreach_adapter = providers.Singleton(BizReachAdapter)

    adapter_registry = providers.Singleton(
        AdapterRegistry,
        adapters=providers.List(bizreach_adapter),
    )

    tenure_evaluator = providers.Singleton(TenureEvaluator)
    salary_evaluator = providers.Singleton(SalaryEvaluator)
    jd_matcher = providers.Singleton(JDMatcher)

    evaluators = providers.List(
        tenure_evaluator,
        salary_evaluator,
        jd_matcher,
    )

    screening_core = providers.Singleton(
        ScreeningCore,
        evaluators=evaluators,
        score_weights=config.score_weights.optional(),
        thresholds=config.thresholds.optional(),
    )

    pipeline = providers.Factory(
        ScreeningPipeline,
        core=screening_core,
        registry=adapter_registry,
    )


def create_container(**settings) -> ScreeningContainer:
    """Instantiate container with optional overrides."""
    container = ScreeningContainer()
    if settings:
        container.config.override(settings)
    return container
