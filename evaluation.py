"""
A lightweight evaluation harness for DocuBot.

This module helps students compare:
- naive generation over the full docs
- retrieval only answers
- RAG answers (retrieval + Gemini)

The evaluation is intentionally simple: it checks whether DocuBot retrieves
the correct files for each query and reports a hit rate.
"""

import argparse
import os
from collections import Counter

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

from dataset import SAMPLE_QUERIES
from answer_validator import AnswerValidator


def parse_external_urls_from_env():
    """Reads external documentation URLs from EXTERNAL_DOC_URLS."""
    raw = os.getenv("EXTERNAL_DOC_URLS", "")
    if not raw.strip():
        return []

    normalized = raw.replace("\n", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def parse_validation_min_score():
    """Reads the validation threshold from VALIDATION_MIN_SCORE."""
    raw = os.getenv("VALIDATION_MIN_SCORE", "0.65").strip()
    try:
        score = float(raw)
    except ValueError:
        score = 0.65
    return max(0.0, min(1.0, score))


# -----------------------------------------------------------
# Expected document signals for evaluation
# -----------------------------------------------------------
# This dictionary maps a query substring to the filename(s)
# that should be relevant. It does NOT need to be perfect.
# It simply gives students a way to measure improvements.
#
# Example:
#   If a query contains the phrase "auth token",
#   evaluation expects AUTH.md to appear in the retrieval results.
#
EXPECTED_SOURCES = {
    "auth token": ["AUTH.md"],
    "environment variables": ["AUTH.md"],
    "database": ["DATABASE.md"],
    "users": ["API_REFERENCE.md"],
    "projects": ["API_REFERENCE.md"],
    "refresh": ["AUTH.md"],
    "users table": ["DATABASE.md"],
}


def expected_files_for_query(query):
    """
    Returns a list of expected filenames based on simple substring matching.
    """
    query_lower = query.lower()
    matches = []
    for key, files in EXPECTED_SOURCES.items():
        if key in query_lower:
            matches.extend(files)
    return matches


# -----------------------------------------------------------
# Evaluation function
# -----------------------------------------------------------

def evaluate_retrieval(bot, top_k=3):
    """
    Runs DocuBot's retrieval system against SAMPLE_QUERIES.
    Returns a tuple: (hit_rate, detailed_results)

    hit_rate: fraction of queries where at least one retrieved snippet's
              filename matched an expected filename.
    detailed_results: list of dictionaries with structured info.
    """
    results = []
    hits = 0

    for query in SAMPLE_QUERIES:
        expected = expected_files_for_query(query)
        retrieved = bot.retrieve(query, top_k=top_k)

        retrieved_files = [fname for fname, _ in retrieved]

        hit = any(f in retrieved_files for f in expected) if expected else False
        if hit:
            hits += 1

        results.append({
            "query": query,
            "expected": expected,
            "retrieved": retrieved_files,
            "hit": hit
        })

    hit_rate = hits / len(SAMPLE_QUERIES)
    return hit_rate, results


def evaluate_groundedness(bot, validator, queries=None, top_k=3):
    """
    Runs validated RAG on queries and reports groundedness pass rate.

    Returns: (pass_rate, detailed_results)
    """
    queries = queries or SAMPLE_QUERIES
    results = []
    passes = 0

    for query in queries:
        outcome = bot.answer_rag_validated(query, validator=validator, top_k=top_k)
        passed = not outcome["blocked"]
        if passed:
            passes += 1

        results.append(
            {
                "query": query,
                "passed": passed,
                "score": outcome["validation"]["score"],
                "method": outcome["validation"]["method"],
                "block_reason": outcome["block_reason"],
            }
        )

    pass_rate = passes / len(queries) if queries else 0.0
    return pass_rate, results


# -----------------------------------------------------------
# Pretty printing
# -----------------------------------------------------------

def print_eval_results(hit_rate, results):
    """
    Nicely formats evaluation results.
    """
    print("\nEvaluation Results")
    print("------------------")
    print(f"Hit rate: {hit_rate:.2f}\n")

    for item in results:
        print(f"Query: {item['query']}")
        print(f"  Expected:  {item['expected']}")
        print(f"  Retrieved: {item['retrieved']}")
        print(f"  Hit:       {item['hit']}")
        print()


def print_groundedness_results(pass_rate, results):
    """Nicely formats groundedness evaluation results."""
    print("\nGroundedness Evaluation")
    print("-----------------------")
    print(f"Pass rate: {pass_rate:.2f}\n")

    for item in results:
        print(f"Query: {item['query']}")
        print(f"  Passed:      {item['passed']}")
        print(f"  Score:       {item['score']:.2f}")
        print(f"  Method:      {item['method']}")
        print(f"  Block reason:{item['block_reason']}")
        print()


def print_block_reason_summary(results):
    """Prints an aggregate summary of block reasons."""
    reasons = Counter(item["block_reason"] or "allowed" for item in results)
    print("Block Reason Summary")
    print("--------------------")
    for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
        print(f"{reason}: {count}")
    print()


def evaluate_validated_external_rag(top_k=3):
    """
    Runs validated External RAG over SAMPLE_QUERIES and reports groundedness.
    If EXTERNAL_DOC_URLS is unset, this still runs against local docs only.
    """
    from docubot import DocuBot

    try:
        from llm_client import GeminiClient
    except Exception:
        GeminiClient = None

    external_urls = parse_external_urls_from_env()
    if not external_urls:
        print("No EXTERNAL_DOC_URLS configured; running validated evaluation on local docs only.\n")

    llm_client = None
    if GeminiClient is not None:
        try:
            llm_client = GeminiClient()
        except RuntimeError as exc:
            print(f"Warning: Gemini client unavailable: {exc}")

    bot = DocuBot(llm_client=llm_client, remote_urls=external_urls)
    validator = AnswerValidator(llm_client=llm_client, min_score=parse_validation_min_score())

    pass_rate, results = evaluate_groundedness(bot, validator, queries=SAMPLE_QUERIES, top_k=top_k)
    print_groundedness_results(pass_rate, results)
    print_block_reason_summary(results)


# -----------------------------------------------------------
# Optional CLI entry point
# -----------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate DocuBot retrieval or validated External RAG.")
    parser.add_argument(
        "--validated-external-rag",
        action="store_true",
        help="Run groundedness evaluation for the validated External RAG pipeline.",
    )
    args = parser.parse_args()

    if args.validated_external_rag:
        print("Running validated External RAG evaluation...\n")
        evaluate_validated_external_rag()
    else:
        from docubot import DocuBot

        print("Running retrieval evaluation...\n")
        bot = DocuBot()

        hit_rate, results = evaluate_retrieval(bot)
        print_eval_results(hit_rate, results)
