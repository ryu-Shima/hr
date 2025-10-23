"\"\"\"Simple JD keyword matcher evaluator.\"\"\""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from rapidfuzz import fuzz

from ...schemas import CandidateProfile, JobDescription


@dataclass
class JDMatcherConfig:
    """Configuration for rule-based JD matching."""

    min_similarity: float = 60.0


class JDMatcher:
    """Evaluate keyword coverage between JD and candidate resume."""

    method = "jd_rule"

    def __init__(self, *, config: JDMatcherConfig | None = None) -> None:
        self._config = config or JDMatcherConfig()

    def evaluate(self, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        profile = CandidateProfile.model_validate(candidate)
        job = JobDescription.model_validate(context["job"])
        overrides = (context.get("evaluation_overrides") or {}).get("jd_keywords", {})
        keyword_groups = self._extract_keywords(context, job, overrides)
        searchable_corpus = self._build_corpus(profile)

        default_weights = {"must": 1.0, "nice": 0.75, "nice_to_have": 0.5}
        override_weights = overrides.get("weights", {}) or {}

        hits: dict[str, list[str]] = {}
        coverage: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for category, keywords in keyword_groups.items():
            if not keywords:
                continue
            matched = self._match_keywords(searchable_corpus, keywords)
            hits[category] = matched
            coverage_value = self._coverage_ratio(keywords, matched)
            coverage[category] = coverage_value
            weight = float(override_weights.get(category, default_weights.get(category, 0.0)))
            if weight <= 0.0:
                continue
            total_weight += weight
            weighted_sum += weight * coverage_value

        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        score = min(max(score, 0.0), 1.0)

        jd_pass = 1.0 if score > 0 else 0.0
        has_bonus_hit = any(hits.get(cat) for cat in ("nice", "nice_to_have"))
        title_bonus = overrides.get("title_bonus", 0.1) if has_bonus_hit else 0.0
        sim_title = max(coverage.get("nice", 0.0), coverage.get("nice_to_have", 0.0))
        embed_sim = score
        bm25_proxy = score

        metadata_weights = {
            "must": default_weights["must"] if "must" not in override_weights else override_weights["must"],
            "nice": default_weights["nice"] if "nice" not in override_weights else override_weights["nice"],
            "nice_to_have": default_weights["nice_to_have"]
            if "nice_to_have" not in override_weights
            else override_weights["nice_to_have"],
        }

        return {
            "method": self.method,
            "scores": {
                "jd_must_coverage": coverage.get("must", 1.0 if not keyword_groups.get("must") else 0.0),
                "jd_nice_coverage": coverage.get("nice", 1.0 if not keyword_groups.get("nice") else 0.0),
                "jd_pass": jd_pass,
                "embed_sim": embed_sim,
                "bm25_prox": bm25_proxy,
                "sim_title": sim_title,
                "title_bonus": title_bonus,
            },
            "metadata": {
                "keywords": keyword_groups,
                "hits": hits,
                "coverage": coverage,
                "corpus_size": len(searchable_corpus),
                "min_similarity": self._config.min_similarity,
                "weights": metadata_weights,
                "title_bonus": title_bonus,
            },
        }

    def _extract_keywords(
        self,
        context: dict[str, Any],
        job: JobDescription,
        overrides: dict[str, Any],
    ) -> dict[str, list[str]]:
        context_keywords = context.get("jd_keywords") or {}
        groups = {
            "must": overrides.get("must"),
            "nice": overrides.get("nice"),
            "nice_to_have": overrides.get("nice_to_have"),
        }
        if groups["must"] is None:
            groups["must"] = context_keywords.get("must") or job.key_phrases or []
        if groups["nice"] is None:
            groups["nice"] = context_keywords.get("nice") or job.role_titles or []
        if groups["nice_to_have"] is None:
            groups["nice_to_have"] = context_keywords.get("nice_to_have") or []
        return {key: [kw.strip() for kw in values if kw] for key, values in groups.items()}

    def _build_corpus(self, profile: CandidateProfile) -> list[str]:
        corpus: list[str] = []
        corpus.extend(profile.skills)
        corpus.extend(lang.language for lang in profile.languages or [])
        for exp in profile.experiences:
            if exp.title:
                corpus.append(exp.title)
            if exp.summary:
                corpus.append(exp.summary)
            corpus.extend(exp.bullets)
        if profile.notes:
            corpus.append(profile.notes)
        return [text.lower() for text in corpus if text]

    def _match_keywords(
        self,
        corpus: Sequence[str],
        keywords: Sequence[str],
    ) -> list[str]:
        matches: list[str] = []
        for keyword in keywords:
            keyword_lower = keyword.lower()
            for text in corpus:
                if keyword_lower in text:
                    matches.append(keyword)
                    break
                if fuzz.token_set_ratio(keyword_lower, text) >= self._config.min_similarity:
                    matches.append(keyword)
                    break
        return matches

    @staticmethod
    def _coverage_ratio(
        keywords: Sequence[str],
        hits: Iterable[str],
    ) -> float:
        total = len(keywords)
        if total == 0:
            return 1.0
        return len(set(hits)) / total
