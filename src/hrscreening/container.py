"\"\"\"Dependency injection container for the screening system.\"\"\""

from __future__ import annotations

from dependency_injector import containers, providers

from .adapters import BizReachAdapter
from .core import (
    BM25ProximityEvaluator,
    EmbeddingSimilarityEvaluator,
    JDMatcher,
    SalaryEvaluator,
    ScreeningCore,
    TenureEvaluator,
)
from .core.evaluators.bm25_proximity import BM25ProximityConfig
from .core.evaluators.embedding_similarity import EmbeddingSimilarityConfig
from .core.evaluators.jd_matcher import JDMatcherConfig
from .core.evaluators.salary import SalaryConfig
from .core.evaluators.tenure import TenureConfig
from .pipeline import AdapterRegistry, ScreeningPipeline


class ScreeningContainer(containers.DeclarativeContainer):
    """Dependency-injector container definition."""

    config = providers.Configuration()

    bizreach_adapter = providers.Singleton(BizReachAdapter)

    adapter_registry = providers.Singleton(
        AdapterRegistry,
        adapters=providers.List(bizreach_adapter),
    )

    bm25_evaluator = providers.Singleton(BM25ProximityEvaluator)
    embed_evaluator = providers.Singleton(EmbeddingSimilarityEvaluator)
    tenure_evaluator = providers.Singleton(TenureEvaluator)
    salary_evaluator = providers.Singleton(SalaryEvaluator)
    jd_matcher = providers.Singleton(JDMatcher)

    evaluators = providers.List(
        bm25_evaluator,
        embed_evaluator,
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


def create_container(*, settings: dict | None = None) -> ScreeningContainer:
    """Instantiate container with optional overrides."""

    container = ScreeningContainer()

    if not settings:
        return container

    core_settings = settings.get("core", {}) if isinstance(settings, dict) else {}
    if core_settings:
        container.config.override(core_settings)

    evaluator_settings = settings.get("evaluators", {}) if isinstance(settings, dict) else {}

    if "bm25" in evaluator_settings:
        bm25_config = BM25ProximityConfig(**evaluator_settings["bm25"])
        container.bm25_evaluator.override(
            providers.Singleton(BM25ProximityEvaluator, config=bm25_config)
        )

    if "embed" in evaluator_settings:
        embed_config = EmbeddingSimilarityConfig(**evaluator_settings["embed"])
        container.embed_evaluator.override(
            providers.Singleton(EmbeddingSimilarityEvaluator, config=embed_config)
        )

    if "tenure" in evaluator_settings:
        tenure_config = TenureConfig(**evaluator_settings["tenure"])
        container.tenure_evaluator.override(
            providers.Singleton(TenureEvaluator, config=tenure_config)
        )

    if "salary" in evaluator_settings:
        salary_config = SalaryConfig(**evaluator_settings["salary"])
        container.salary_evaluator.override(
            providers.Singleton(SalaryEvaluator, config=salary_config)
        )

    if "jd" in evaluator_settings:
        jd_config = JDMatcherConfig(**evaluator_settings["jd"])
        container.jd_matcher.override(providers.Singleton(JDMatcher, config=jd_config))

    return container
