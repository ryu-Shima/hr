"\"\"\"Embedding similarity evaluator using lightweight TF-IDF cosine.\"\"\""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from ...schemas import CandidateProfile, JobDescription

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[ぁ-んァ-ン一-龥]+")


@dataclass
class EmbeddingSimilarityConfig:
    """Configuration for embedding similarity evaluator."""

    top_k: int = 3
    section_weights: dict[str, float] = None  # type: ignore[assignment]
    synonyms: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        if self.section_weights is None:
            self.section_weights = {
                "bullets": 1.0,
                "summary": 0.8,
                "title": 0.7,
            }
        if self.synonyms is None:
            self.synonyms = {}


class EmbeddingSimilarityEvaluator:
    """Approximate embedding similarity using manual TF-IDF cosine distance."""

    method = "embed_similarity"

    def __init__(self, *, config: EmbeddingSimilarityConfig | None = None) -> None:
        self._config = config or EmbeddingSimilarityConfig()

    def evaluate(self, candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        profile = CandidateProfile.model_validate(candidate)
        job = JobDescription.model_validate(context["job"])

        jd_texts = [text for text in (job.requirements_text or []) if text]
        if not jd_texts:
            return self._empty_payload()

        resume_entries = self._collect_resume_entries(profile)
        if not resume_entries:
            return self._empty_payload()

        augmented_jd_texts = [self._augment_text(text) for text in jd_texts]
        corpus = [self._tokenize(text) for text in augmented_jd_texts]
        resume_tokens = [self._tokenize(entry["augmented_text"]) for entry in resume_entries]

        if not any(corpus) or not any(resume_tokens):
            return self._empty_payload()

        idf = self._compute_idf(corpus + resume_tokens)
        jd_vectors = [self._tfidf_vector(tokens, idf) for tokens in corpus]
        resume_vectors = [self._tfidf_vector(tokens, idf) for tokens in resume_tokens]

        similarity_matrix = [
            [self._cosine_similarity(jd_vec, resume_vec) for resume_vec in resume_vectors]
            for jd_vec in jd_vectors
        ]

        evidence = self._collect_evidence(jd_texts, resume_entries, similarity_matrix)

        if not evidence:
            return self._empty_payload()

        top_k = self._config.top_k
        avg_similarity = sum(item["similarity"] for item in evidence[:top_k]) / min(len(evidence), top_k)
        title_similarity = self._title_similarity(job, profile, idf)

        return {
            "method": self.method,
            "scores": {
                "embed_sim": round(avg_similarity, 4),
                "sim_title": round(title_similarity, 4),
            },
            "metadata": {
                "model": "tfidf-cosine-lite",
                "top_k": top_k,
                "evidence_pairs": evidence[:top_k],
            },
        }

    def _collect_resume_entries(self, profile: CandidateProfile) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for exp in profile.experiences or []:
            if exp.title:
                entries.append(
                    {
                        "text": exp.title,
                        "augmented_text": self._augment_text(exp.title),
                        "section": "title",
                        "weight": self._config.section_weights["title"],
                    }
                )
            if exp.summary:
                entries.append(
                    {
                        "text": exp.summary,
                        "augmented_text": self._augment_text(exp.summary),
                        "section": "summary",
                        "weight": self._config.section_weights["summary"],
                    }
                )
            for bullet in exp.bullets or []:
                entries.append(
                    {
                        "text": bullet,
                        "augmented_text": self._augment_text(bullet),
                        "section": "bullets",
                        "weight": self._config.section_weights["bullets"],
                    }
                )
        return [entry for entry in entries if entry["text"]]

    def _collect_evidence(
        self,
        jd_texts: list[str],
        resume_entries: list[dict[str, Any]],
        similarity_matrix: list[list[float]],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for jd_index, jd_text in enumerate(jd_texts):
            sims = similarity_matrix[jd_index]
            for entry, similarity in zip(resume_entries, sims):
                if similarity <= 0:
                    continue
                evidence.append(
                    {
                        "jd_text": jd_text,
                        "resume_text": entry["text"],
                        "similarity": float(similarity),
                        "section": entry["section"],
                        "weight": entry["weight"],
                    }
                )
        evidence.sort(key=lambda item: item["similarity"], reverse=True)
        return evidence

    def _title_similarity(
        self,
        job: JobDescription,
        profile: CandidateProfile,
        idf: dict[str, float],
    ) -> float:
        if not job.role_titles:
            return 0.0
        candidate_titles = [exp.title for exp in profile.experiences or [] if exp.title]
        if not candidate_titles:
            return 0.0

        job_vectors = [self._tfidf_vector(self._tokenize(self._augment_text(text)), idf) for text in job.role_titles]
        candidate_vectors = [self._tfidf_vector(self._tokenize(self._augment_text(text)), idf) for text in candidate_titles]
        best = 0.0
        for job_vec in job_vectors:
            for candidate_vec in candidate_vectors:
                best = max(best, self._cosine_similarity(job_vec, candidate_vec))
        return best

    def _tfidf_vector(self, tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        total = sum(tf.values())
        vector: dict[str, float] = {}
        for token, count in tf.items():
            weight = (count / total) * idf.get(token, 0.0)
            if weight > 0:
                vector[token] = weight
        return vector

    def _compute_idf(self, documents: Iterable[list[str]]) -> dict[str, float]:
        doc_freq: dict[str, int] = {}
        total_docs = 0
        for tokens in documents:
            if not tokens:
                continue
            total_docs += 1
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        idf: dict[str, float] = {}
        for token, freq in doc_freq.items():
            idf[token] = math.log((1 + total_docs) / (1 + freq)) + 1
        return idf

    def _cosine_similarity(self, vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        dot = sum(value * vec_b.get(token, 0.0) for token, value in vec_a.items())
        if dot == 0:
            return 0.0
        norm_a = math.sqrt(sum(value * value for value in vec_a.values()))
        norm_b = math.sqrt(sum(value * value for value in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _tokenize(self, text: str) -> list[str]:
        tokens = _TOKEN_PATTERN.findall(text.lower())
        normalized: list[str] = []
        for token in tokens:
            if token in {"iac", "infrastructureascode"}:
                normalized.append("iac")
            elif token in {"aws", "amazonwebservices"}:
                normalized.append("aws")
            else:
                normalized.append(token)
        return normalized

    def _augment_text(self, text: str) -> str:
        tokens = self._tokenize(text)
        synonyms = self._config.synonyms or {}
        extras: list[str] = []
        for token in tokens:
            extras.extend(synonyms.get(token, []))
        if extras:
            return text + " " + " ".join(sorted(set(extras)))
        return text

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "scores": {"embed_sim": 0.0, "sim_title": 0.0},
            "metadata": {"model": "tfidf-cosine-lite", "top_k": self._config.top_k, "evidence_pairs": []},
        }
