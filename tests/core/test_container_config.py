from __future__ import annotations

from hrscreening.container import create_container
from hrscreening.schemas.config import AppConfig, load_config


def test_create_container_with_overrides():
    container = create_container(
        settings={
            "core": {"score_weights": {"bm25_prox": 0.55, "embed_sim": 0.25}},
            "evaluators": {
                "bm25": {"window": 5},
                "embed": {"top_k": 4},
                "tenure": {"average_threshold_months": 24},
                "salary": {"tolerance_ratio": 0.15},
            },
        }
    )

    bm25 = container.bm25_evaluator()
    embed = container.embed_evaluator()
    tenure = container.tenure_evaluator()
    salary = container.salary_evaluator()
    core = container.screening_core()

    assert bm25._config.window == 5
    assert embed._config.top_k == 4
    assert tenure._config.average_threshold_months == 24
    assert salary._config.tolerance_ratio == 0.15
    assert core._score_weights["bm25_prox"] == 0.55
    assert core._score_weights["embed_sim"] == 0.25


def test_load_config_validation():
    data = {
        "core": {"score_weights": {"bm25_prox": 0.6}},
        "evaluators": {"bm25": {"window": 6}},
    }
    app_config = load_config(data)
    assert isinstance(app_config, AppConfig)
    settings = app_config.to_settings()
    assert settings["core"]["score_weights"]["bm25_prox"] == 0.6
