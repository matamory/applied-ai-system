"""Validation utilities for checking whether answers are grounded in snippets."""

from __future__ import annotations

import re


class AnswerValidator:
    """Scores answer groundedness and applies a configurable pass threshold."""

    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "that", "the", "to",
        "was", "what", "when", "where", "which", "who", "why", "with",
        "this", "these", "those", "there", "their", "then", "than", "also",
        "system", "application", "example",
    }

    def __init__(self, llm_client, min_score=0.65):
        self.llm_client = llm_client
        self.min_score = min_score

    def _tokenize(self, text):
        return re.findall(r"\b\w+\b", (text or "").lower())

    def _query_keywords(self, query):
        return [
            token
            for token in self._tokenize(query)
            if len(token) > 2 and token not in self.STOPWORDS
        ]

    def _heuristic_groundedness(self, query, answer, snippets):
        query_keywords = set(self._query_keywords(query))
        snippet_text = " ".join(text.lower() for _, text in snippets)
        snippet_tokens = set(self._tokenize(snippet_text))
        answer_tokens = set(self._tokenize(answer))

        if not answer_tokens or not query_keywords:
            return 0.0

        # First gate: snippets must cover enough query meaning.
        matched_query_keywords = query_keywords.intersection(snippet_tokens)
        matched_count = len(matched_query_keywords)
        required = 1 if len(query_keywords) == 1 else 2
        if matched_count < required:
            return 0.0

        # Heuristic fallback: overlap between answer and available evidence/query.
        evidence_hits = sum(1 for token in answer_tokens if token in snippet_tokens)
        query_hits = sum(1 for token in answer_tokens if token in query_keywords)

        evidence_ratio = evidence_hits / len(answer_tokens)
        query_ratio = query_hits / len(answer_tokens)
        coverage_ratio = matched_count / len(query_keywords)
        score = 0.60 * evidence_ratio + 0.25 * query_ratio + 0.15 * coverage_ratio
        return max(0.0, min(1.0, score))

    def validate(self, query, answer, snippets):
        """
        Returns validation metadata:
        {
            "score": float,
            "is_grounded": bool,
            "reason": str,
            "method": "llm" | "heuristic",
        }
        """
        llm_result = None
        if self.llm_client is not None:
            try:
                llm_result = self.llm_client.validate_grounded_answer(query, answer, snippets)
            except Exception:
                llm_result = None

        if llm_result is not None:
            score = float(llm_result.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            reason = llm_result.get("reason", "Validation completed.")
            is_grounded = score >= self.min_score and bool(llm_result.get("is_grounded", True))
            return {
                "score": score,
                "is_grounded": is_grounded,
                "reason": reason,
                "method": "llm",
            }

        score = self._heuristic_groundedness(query, answer, snippets)
        return {
            "score": score,
            "is_grounded": score >= self.min_score,
            "reason": "Heuristic validation fallback used.",
            "method": "heuristic",
        }
