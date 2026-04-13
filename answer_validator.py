"""Validation utilities for checking whether answers are grounded in snippets."""

from __future__ import annotations


class AnswerValidator:
    """Scores answer groundedness and applies a configurable pass threshold."""

    def __init__(self, llm_client, min_score=0.65):
        self.llm_client = llm_client
        self.min_score = min_score

    def _heuristic_groundedness(self, query, answer, snippets):
        query_tokens = set(query.lower().split())
        snippet_text = " ".join(text.lower() for _, text in snippets)
        answer_tokens = set(answer.lower().split())

        if not answer_tokens:
            return 0.0

        # Heuristic fallback: overlap between answer and available evidence/query.
        evidence_hits = sum(1 for token in answer_tokens if token in snippet_text)
        query_hits = sum(1 for token in answer_tokens if token in query_tokens)

        evidence_ratio = evidence_hits / len(answer_tokens)
        query_ratio = query_hits / len(answer_tokens)
        return max(0.0, min(1.0, 0.85 * evidence_ratio + 0.15 * query_ratio))

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
