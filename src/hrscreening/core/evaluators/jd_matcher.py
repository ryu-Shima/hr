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
        must_keywords, nice_keywords = self._extract_keywords(context, job)
        searchable_corpus = self._build_corpus(profile)

        must_hits = self._match_keywords(searchable_corpus, must_keywords)
        nice_hits = self._match_keywords(searchable_corpus, nice_keywords)

        must_coverage = self._coverage_ratio(must_keywords, must_hits)
        nice_coverage = self._coverage_ratio(nice_keywords, nice_hits)
        passes = must_coverage >= 1.0

        title_bonus = 0.1 if passes else 0.0
        sim_title = max(nice_coverage, 0.6 if passes else 0.0)
        embed_sim = max(must_coverage, nice_coverage)
        bm25_proxy = must_coverage

        return {
            "method": self.method,
            "scores": {
                "jd_must_coverage": must_coverage,
                "jd_nice_coverage": nice_coverage,
                "jd_pass": 1.0 if passes else 0.0,
                "embed_sim": embed_sim,
                "bm25_prox": bm25_proxy,
                "sim_title": sim_title,
                "title_bonus": title_bonus,
            },
            "metadata": {
                "must_keywords": must_keywords,
                "nice_keywords": nice_keywords,
                "must_hits": must_hits,
                "nice_hits": nice_hits,
                "corpus_size": len(searchable_corpus),
                "min_similarity": self._config.min_similarity,
            },
        }

    def _extract_keywords(
        self,
        context: dict[str, Any],
        job: JobDescription,
    ) -> tuple[list[str], list[str]]:
        context_keywords = context.get("jd_keywords") or {}
        must_keywords = context_keywords.get("must") or job.key_phrases or []
        nice_keywords = context_keywords.get("nice") or job.role_titles or []
        return (
            [kw.strip() for kw in must_keywords if kw],
            [kw.strip() for kw in nice_keywords if kw],
        )

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
