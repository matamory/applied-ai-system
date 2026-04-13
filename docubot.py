"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import re

from doc_fetcher import load_external_documents


class DocuBot:
    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "that", "the", "to",
        "was", "what", "when", "where", "which", "who", "why", "with",
    }

    def __init__(
        self,
        docs_folder="docs",
        llm_client=None,
        remote_urls=None,
        use_remote_cache=True,
    ):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        remote_urls: optional list of external docs URLs
        use_remote_cache: whether to read/write external docs cache
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client
        self.remote_urls = remote_urls or []
        self.use_remote_cache = use_remote_cache
        self.external_fetch_failures = []

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Split docs into smaller retrieval units (filename, section_text)
        self.sections = self.build_sections(self.documents)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.sections)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))

        external_docs, failures = load_external_documents(
            self.remote_urls,
            use_cache=self.use_remote_cache,
        )
        self.external_fetch_failures = failures
        docs.extend(external_docs)

        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def _tokenize(self, text):
        """Lowercase and split text into simple word tokens."""
        return re.findall(r"\b\w+\b", text.lower())

    def _query_keywords(self, query):
        """Return informative query tokens after removing common filler words."""
        return [
            token
            for token in self._tokenize(query)
            if len(token) > 2 and token not in self.STOPWORDS
        ]

    def has_meaningful_evidence(self, query, snippets):
        """
        Guardrail for refusal behavior.

        "Meaningful evidence" means at least one retrieved snippet contains
        enough informative query keywords.
        - If query has 1 keyword, require 1 match.
        - If query has 2+ keywords, require 2 distinct matches.
        """
        if not snippets:
            return False

        keywords = self._query_keywords(query)
        if not keywords:
            return False

        required_overlap = 1 if len(keywords) == 1 else 2
        keyword_set = set(keywords)

        for _, text in snippets:
            snippet_tokens = set(self._tokenize(text))
            overlap_count = len(keyword_set.intersection(snippet_tokens))
            if overlap_count >= required_overlap:
                return True

        return False

    def build_sections(self, documents):
        """
        Split each document into smaller sections using blank lines.
        Returns a list of tuples: (filename, section_text)
        """
        sections = []
        for filename, text in documents:
            # Split on one or more blank lines, keep non-empty trimmed sections.
            parts = re.split(r"\n\s*\n+", text)
            for part in parts:
                section = part.strip()
                if section:
                    sections.append((filename, section))
        return sections

    def build_index(self, sections):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to section ids
        they appear in.

        Example structure:
        {
            "token": [0, 4, 12],
            "database": [3, 9]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}

        for section_id, (_, text) in enumerate(sections):
            # Use a set so each section id appears once per token.
            unique_tokens = set(self._tokenize(text))
            for token in unique_tokens:
                index.setdefault(token, set()).add(section_id)

        # Convert sets to sorted lists for deterministic retrieval.
        return {token: sorted(section_ids) for token, section_ids in index.items()}

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        query_tokens = self._query_keywords(query)
        if not query_tokens:
            return 0

        token_counts = {}
        for token in self._tokenize(text):
            token_counts[token] = token_counts.get(token, 0) + 1

        score = 0
        for token in query_tokens:
            score += token_counts.get(token, 0)

        return score

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        query_tokens = self._query_keywords(query)
        if not query_tokens:
            return []

        # Get candidate section ids from the inverted index.
        candidate_sections = set()
        for token in query_tokens:
            for section_id in self.index.get(token, []):
                candidate_sections.add(section_id)

        if not candidate_sections:
            return []

        scored = []
        for section_id in candidate_sections:
            filename, text = self.sections[section_id]
            score = self.score_document(query, text)
            if score > 0:
                scored.append((score, section_id, filename, text))

        scored.sort(key=lambda item: (-item[0], item[2], item[1]))
        results = [(filename, text) for _, _, filename, text in scored]
        return results[:top_k]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not self.has_meaningful_evidence(query, snippets):
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not self.has_meaningful_evidence(query, snippets):
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    def answer_rag_validated(self, query, validator, top_k=3):
        """
        RAG mode with hard validation guardrail.

        Returns a structured dict with answer, snippets, validation metadata,
        and final disposition.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "Validated RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not self.has_meaningful_evidence(query, snippets):
            return {
                "query": query,
                "snippets": snippets,
                "raw_answer": None,
                "final_answer": (
                    "I could not find enough reliable evidence in the available docs. "
                    "Please rephrase your question or narrow the scope."
                ),
                "blocked": True,
                "block_reason": "insufficient_evidence",
                "validation": {
                    "score": 0.0,
                    "is_grounded": False,
                    "reason": "Insufficient retrieval evidence before generation.",
                    "method": "rule",
                },
            }

        raw_answer = self.llm_client.answer_from_snippets(query, snippets)
        validation = validator.validate(query, raw_answer, snippets)

        if not validation.get("is_grounded", False):
            return {
                "query": query,
                "snippets": snippets,
                "raw_answer": raw_answer,
                "final_answer": (
                    "I cannot confidently validate this answer against the retrieved docs. "
                    "Please rephrase your question or ask for a narrower topic."
                ),
                "blocked": True,
                "block_reason": "validation_failed",
                "validation": validation,
            }

        return {
            "query": query,
            "snippets": snippets,
            "raw_answer": raw_answer,
            "final_answer": raw_answer,
            "blocked": False,
            "block_reason": None,
            "validation": validation,
        }

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
