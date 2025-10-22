"\"\"\"Pydantic configuration schema for CLI YAML input.\"\"\""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError


class CoreConfig(BaseModel):
    score_weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None


class EvaluatorConfig(BaseModel):
    bm25: dict[str, Any] | None = None
    embed: dict[str, Any] | None = None
    tenure: dict[str, Any] | None = None
    salary: dict[str, Any] | None = None
    jd: dict[str, Any] | None = None


class AppConfig(BaseModel):
    core: CoreConfig = Field(default_factory=CoreConfig)
    evaluators: EvaluatorConfig = Field(default_factory=EvaluatorConfig)

    def to_settings(self) -> dict[str, Any]:
        settings: dict[str, Any] = {}
        if self.core.score_weights or self.core.thresholds:
            settings["core"] = self.core.model_dump(exclude_none=True)
        evaluator_settings = self.evaluators.model_dump(exclude_none=True)
        if evaluator_settings:
            settings["evaluators"] = evaluator_settings
        return settings


def load_config(raw: Any) -> AppConfig:
    if not isinstance(raw, dict):
        raise ValidationError([{"type": "type_error.dict", "loc": ("config",), "msg": "Config must be a mapping"}], AppConfig)
    return AppConfig.model_validate(raw)

