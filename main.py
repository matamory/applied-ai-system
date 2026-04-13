"""
CLI runner for the DocuBot tinker activity.

Supports three modes:
1. Naive LLM generation over all docs (Phase 0)
2. Retrieval only (Phase 1)
3. RAG: retrieval plus LLM generation (Phase 2)
4. External RAG: include external docs URLs in retrieval pipeline
"""

import os

from dotenv import load_dotenv
load_dotenv()

from docubot import DocuBot
from llm_client import GeminiClient
from dataset import SAMPLE_QUERIES
from answer_validator import AnswerValidator
from run_logger import RunLogger


def try_create_llm_client():
    """
    Tries to create a GeminiClient.
    Returns (llm_client, has_llm: bool).
    """
    try:
        client = GeminiClient()
        return client, True
    except RuntimeError as exc:
        print("Warning: LLM features are disabled.")
        print(f"Reason: {exc}")
        print("You can still run retrieval only mode.\n")
        return None, False


def choose_mode(has_llm):
    """
    Asks the user which mode to run.
    Returns "1", "2", "3", or "q".
    """
    print("Choose a mode:")
    if has_llm:
        print("  1) Naive LLM over full docs (no retrieval)")
    else:
        print("  1) Naive LLM over full docs (unavailable, no GEMINI_API_KEY)")
    print("  2) Retrieval only (no LLM)")
    if has_llm:
        print("  3) RAG (retrieval + LLM)")
    else:
        print("  3) RAG (unavailable, no GEMINI_API_KEY)")
    if has_llm:
        print("  4) External RAG (local docs + external URLs + LLM)")
    else:
        print("  4) External RAG (unavailable, no GEMINI_API_KEY)")
    print("  q) Quit")

    choice = input("Enter choice: ").strip().lower()
    return choice


def get_query_or_use_samples():
    """
    Ask the user if they want to run all sample queries or a single custom query.

    Returns:
        queries: list of strings
        label: short description of the source of queries
    """
    print("\nPress Enter to run built in sample queries.")
    custom = input("Or type a single custom query: ").strip()

    if custom:
        return [custom], "custom query"
    else:
        return SAMPLE_QUERIES, "sample queries"


def run_naive_llm_mode(bot, has_llm):
    """
    Mode 1:
    Naive LLM generation over the full docs corpus.
    """
    if not has_llm or bot.llm_client is None:
        print("\nNaive LLM mode is not available (no GEMINI_API_KEY).\n")
        return

    queries, label = get_query_or_use_samples()
    print(f"\nRunning naive LLM mode on {label}...\n")

    all_text = bot.full_corpus_text()

    for query in queries:
        print("=" * 60)
        print(f"Question: {query}\n")
        answer = bot.llm_client.naive_answer_over_full_docs(query, all_text)
        print("Answer:")
        print(answer)
        print()


def run_retrieval_only_mode(bot):
    """
    Mode 2:
    Retrieval only answers. No LLM involved.
    """
    queries, label = get_query_or_use_samples()
    print(f"\nRunning retrieval only mode on {label}...\n")

    for query in queries:
        print("=" * 60)
        print(f"Question: {query}\n")
        answer = bot.answer_retrieval_only(query)
        print("Retrieved snippets:")
        print(answer)
        print()


def run_rag_mode(bot, has_llm):
    """
    Mode 3:
    Retrieval plus LLM generation.
    """
    if not has_llm or bot.llm_client is None:
        print("\nRAG mode is not available (no GEMINI_API_KEY).\n")
        return

    queries, label = get_query_or_use_samples()
    print(f"\nRunning RAG mode on {label}...\n")

    for query in queries:
        print("=" * 60)
        print(f"Question: {query}\n")
        answer = bot.answer_rag(query)
        print("Answer:")
        print(answer)
        print()


def parse_external_urls_from_env():
    """
    Reads external documentation URLs from EXTERNAL_DOC_URLS.
    Supports comma-separated or newline-separated values.
    """
    raw = os.getenv("EXTERNAL_DOC_URLS", "")
    if not raw.strip():
        return []

    # Normalize commas/newlines into a single separator.
    normalized = raw.replace("\n", ",")
    urls = [part.strip() for part in normalized.split(",") if part.strip()]
    return urls


def parse_validation_min_score():
    raw = os.getenv("VALIDATION_MIN_SCORE", "0.65").strip()
    try:
        score = float(raw)
    except ValueError:
        score = 0.65
    return max(0.0, min(1.0, score))


def parse_log_path():
    return os.getenv("DOCUBOT_LOG_PATH", "logs/external_rag_runs.jsonl").strip()


def run_external_rag_mode(llm_client, has_llm):
    """
    Mode 4:
    RAG answers over local docs plus external docs fetched from URLs.
    """
    if not has_llm or llm_client is None:
        print("\nExternal RAG mode is not available (no GEMINI_API_KEY).\n")
        return

    external_urls = parse_external_urls_from_env()
    if not external_urls:
        print("\nExternal RAG mode requires EXTERNAL_DOC_URLS in .env or shell.")
        print("Example:")
        print("EXTERNAL_DOC_URLS=https://example.com/docs,https://example.com/api\n")
        return

    bot = DocuBot(llm_client=llm_client, remote_urls=external_urls)
    validator = AnswerValidator(llm_client=llm_client, min_score=parse_validation_min_score())
    logger = RunLogger(log_path=parse_log_path(), enabled=True)

    if bot.external_fetch_failures:
        print("\nWarning: Some external docs could not be fetched and had no cache fallback:")
        for url, reason in bot.external_fetch_failures:
            print(f"  - {url} ({reason})")
        print()

    queries, label = get_query_or_use_samples()
    print(f"\nRunning external RAG mode on {label}...\n")

    for query in queries:
        print("=" * 60)
        print(f"Question: {query}\n")
        outcome = bot.answer_rag_validated(query, validator=validator)
        answer = outcome["final_answer"]
        print("Answer:")
        print(answer)
        print(
            f"Validation: score={outcome['validation']['score']:.2f}, "
            f"method={outcome['validation']['method']}, blocked={outcome['blocked']}"
        )

        logger.log(
            {
                "mode": "external_rag_validated",
                "query": query,
                "remote_urls": external_urls,
                "external_fetch_failures": bot.external_fetch_failures,
                "retrieved_files": [filename for filename, _ in outcome["snippets"]],
                "retrieved_count": len(outcome["snippets"]),
                "validation": outcome["validation"],
                "blocked": outcome["blocked"],
                "block_reason": outcome["block_reason"],
                "final_answer": outcome["final_answer"],
            }
        )
        print()


def main():
    print("DocuBot Tinker Activity")
    print("=======================\n")

    llm_client, has_llm = try_create_llm_client()
    bot = DocuBot(llm_client=llm_client)

    while True:
        choice = choose_mode(has_llm)

        if choice == "q":
            print("\nGoodbye.")
            break
        elif choice == "1":
            run_naive_llm_mode(bot, has_llm)
        elif choice == "2":
            run_retrieval_only_mode(bot)
        elif choice == "3":
            run_rag_mode(bot, has_llm)
        elif choice == "4":
            run_external_rag_mode(llm_client, has_llm)
        else:
            print("\nUnknown choice. Please pick 1, 2, 3, 4, or q.\n")


if __name__ == "__main__":
    main()
