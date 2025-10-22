from __future__ import annotations

from hrscreening.container import create_container


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
