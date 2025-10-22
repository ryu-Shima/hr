"\"\"\"BM25 proximity-based evaluator.\"\"\""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

from rapidfuzz import fuzz

from ...schemas import CandidateProfile, JobDescription

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[ぁ-んァ-ン一-龥]+")


@dataclass
class BM25ProximityConfig:
    """Configuration parameters for BM25 proximity evaluator."""

    k1: float = 1.2
    b: float = 0.75
    alpha_proximity: float = 0.2
    window: int = 8
    section_weights: dict[str, float] = None  # type: ignore[assignment]
    synonyms: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        if self.section_weights is None:
            self.section_weights = {
                "bullets": 1.0,
                "summary": 0.6,
                "title": 0.8,
                "skills": 0.5,
            }
        if self.synonyms is None:
            self.synonyms = {}


class BM25ProximityEvaluator:
    """Compute BM25-based matching score between JD and candidate corpus."""

    method = "bm25_proximity"

    def __init__(self, *, config: BM25ProximityConfig | None = None) -> None:
        self._config = config or BM25ProximityConfig()

    def evaluate(self, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        profile = CandidateProfile.model_validate(candidate)
        job = JobDescription.model_validate(context["job"])

        docs = self._build_documents(profile)
        if not docs:
            return self._empty_payload()

        token_docs = [doc["tokens"] for doc in docs]
        avg_doc_len = sum(len(tokens) for tokens in token_docs) / len(token_docs)
        idf = self._compute_idf(token_docs)

        hits: list[dict[str, Any]] = []
        total_score = 0.0

        queries = self._build_queries(job)
        for query in queries:
            query_tokens = self._expand_tokens(self._tokenize(query))
            if not query_tokens:
                continue
            best_hit = self._score_query(
                query_text=query,
                query_tokens=query_tokens,
                docs=docs,
                idf=idf,
                avg_doc_len=avg_doc_len,
            )
            if best_hit is None:
                continue
            hits.append(best_hit)
            total_score += best_hit["bm25"] + best_hit["proximity_bonus"]

        bm25_score = total_score / len(hits) if hits else 0.0
        title_bonus = self._compute_title_bonus(profile, job)

        return {
            "method": self.method,
            "scores": {
                "bm25_prox": bm25_score,
                "title_bonus": title_bonus,
            },
            "metadata": {
                "k1": self._config.k1,
                "b": self._config.b,
                "alpha_proximity": self._config.alpha_proximity,
                "window": self._config.window,
                "hits": hits,
            },
        }

    def _build_documents(self, profile: CandidateProfile) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []

        for exp in profile.experiences or []:
            if exp.title:
                docs.append(
                    {
                        "text": exp.title,
                        "section": "title",
                        "weight": self._config.section_weights["title"],
                    }
                )
            if exp.summary:
                docs.append(
                    {
                        "text": exp.summary,
                        "section": "summary",
                        "weight": self._config.section_weights["summary"],
                    }
                )
            for bullet in exp.bullets or []:
                docs.append(
                    {
                        "text": bullet,
                        "section": "bullets",
                        "weight": self._config.section_weights["bullets"],
                    }
                )

        if profile.skills:
            docs.append(
                {
                    "text": " ".join(profile.skills),
                    "section": "skills",
                    "weight": self._config.section_weights["skills"],
                }
            )

        for doc in docs:
            doc["tokens"] = self._tokenize(doc["text"])

        return [doc for doc in docs if doc["tokens"]]

    def _build_queries(self, job: JobDescription) -> list[str]:
        queries = list(job.requirements_text or [])
        queries.extend(job.key_phrases or [])
        # remove duplicates while preserving order
        seen: set[str] = set()
        unique_queries: list[str] = []
        for text in queries:
            tokenized = " ".join(self._tokenize(text))
            if not tokenized or tokenized in seen:
                continue
            seen.add(tokenized)
            unique_queries.append(text)
        return unique_queries

    def _expand_tokens(self, tokens: list[str]) -> list[str]:
        expanded = set(tokens)
        for token in list(expanded):
            for alt in self._config.synonyms.get(token, []):
                expanded.update(self._tokenize(alt))
        return list(expanded)

    def _score_query(
        self,
        *,
        query_text: str,
        query_tokens: list[str],
        docs: list[dict[str, Any]],
        idf: dict[str, float],
        avg_doc_len: float,
    ) -> dict[str, Any] | None:
        best_score = 0.0
        best_hit: dict[str, Any] | None = None
        for doc in docs:
            tokens = doc["tokens"]
            doc_len = len(tokens)
            bm25 = 0.0
            for token in query_tokens:
                freq = tokens.count(token)
                if freq == 0:
                    continue
                token_idf = idf.get(token, 0.0)
                denom = freq + self._config.k1 * (1 - self._config.b + self._config.b * (doc_len / avg_doc_len))
                bm25 += token_idf * (freq * (self._config.k1 + 1)) / denom
            if bm25 <= 0:
                continue
            proximity = self._proximity_bonus(tokens, query_tokens)
            weighted = (bm25 + proximity) * doc["weight"]
            if weighted > best_score:
                best_score = weighted
                best_hit = {
                    "jd_text": query_text,
                    "resume_text": doc["text"],
                    "bm25": bm25,
                    "proximity_bonus": proximity,
                    "section": doc["section"],
                    "weight": doc["weight"],
                }
        return best_hit

    def _proximity_bonus(self, doc_tokens: list[str], query_tokens: list[str]) -> float:
        if len(query_tokens) <= 1:
            return 0.0
        positions = {token: [] for token in set(query_tokens)}
        for idx, token in enumerate(doc_tokens):
            if token in positions:
                positions[token].append(idx)
        if any(not pos for pos in positions.values()):
            return 0.0
        # compute minimal span covering all tokens
        min_span = math.inf
        for start_token, start_positions in positions.items():
            for start_idx in start_positions:
                max_idx = start_idx
                for token, token_positions in positions.items():
                    best = min(token_positions, key=lambda pos: abs(pos - start_idx))
                    max_idx = max(max_idx, best)
                span = max_idx - start_idx + 1
                if span < min_span:
                    min_span = span
        if min_span is math.inf:
            return 0.0
        if min_span <= self._config.window:
            return self._config.alpha_proximity / (1 + min_span)
        return 0.0

    def _compute_idf(self, docs: Iterable[list[str]]) -> dict[str, float]:
        df: dict[str, int] = {}
        total_docs = 0
        for tokens in docs:
            total_docs += 1
            seen_tokens = set(tokens)
            for token in seen_tokens:
                df[token] = df.get(token, 0) + 1
        idf: dict[str, float] = {}
        for token, freq in df.items():
            idf[token] = math.log(1 + (total_docs - freq + 0.5) / (freq + 0.5))
        return idf

    def _compute_title_bonus(self, profile: CandidateProfile, job: JobDescription) -> float:
        if not job.role_titles:
            return 0.0
        candidate_titles = [exp.title for exp in profile.experiences or [] if exp.title]
        if not candidate_titles:
            return 0.0
        best = 0.0
        for job_title in job.role_titles:
            for candidate_title in candidate_titles:
                ratio = fuzz.token_set_ratio(job_title, candidate_title) / 100.0
                best = max(best, ratio)
        return round(best * 0.2, 4)

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = _TOKEN_PATTERN.findall(text)
        # simple canonicalization for IaC etc.
        normalized: list[str] = []
        for token in tokens:
            if token in {"iac", "infrastructureascode"}:
                normalized.append("iac")
            elif token in {"aws", "amazonwebservices"}:
                normalized.append("aws")
            else:
                normalized.append(token)
        return normalized

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "scores": {"bm25_prox": 0.0, "title_bonus": 0.0},
            "metadata": {
                "k1": self._config.k1,
                "b": self._config.b,
                "alpha_proximity": self._config.alpha_proximity,
                "window": self._config.window,
                "hits": [],
            },
        }
