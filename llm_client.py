"""
Gemini client wrapper used by DocuBot.

Handles:
- Configuring the Gemini client from the GEMINI_API_KEY environment variable
- Naive "generation only" answers over the full docs corpus (Phase 0)
- RAG style answers that use only retrieved snippets (Phase 2)

Experiment with:
- Prompt wording
- Refusal conditions
- How strictly the model is instructed to use only the provided context
"""

import json
import os
import re
import google.generativeai as genai

# Central place to update the model name if needed.
# You can swap this for a different Gemini model in the future.
GEMINI_MODEL_NAME = "gemini-2.5-flash"


class GeminiClient:
    """
    Simple wrapper around the Gemini model.

    Usage:
        client = GeminiClient()
        answer = client.naive_answer_over_full_docs(query, all_text)
        # or
        answer = client.answer_from_snippets(query, snippets)
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY environment variable. "
                "Set it in your shell or .env file to enable LLM features."
            )

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL_NAME)

    # -----------------------------------------------------------
    # Phase 0: naive generation over full docs
    # -----------------------------------------------------------

    def naive_answer_over_full_docs(self, query, all_text):
        # Baseline mode: provide entire corpus so the model can answer directly.
        prompt = f"""
You are a documentation assistant.

Use only the documentation below to answer the question. If the docs do not
contain the answer, reply exactly: "I do not know based on the docs I have."

Documentation:
{all_text}

Developer question:
{query}
    """
        response = self.model.generate_content(prompt)
        return (response.text or "").strip()

    def _extract_json_object(self, text):
        if not text:
            return None
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    # -----------------------------------------------------------
    # Phase 2: RAG style generation over retrieved snippets
    # -----------------------------------------------------------

    def answer_from_snippets(self, query, snippets):
        """
        Phase 2:
        Generate an answer using only the retrieved snippets.

        snippets: list of (filename, text) tuples selected by DocuBot.retrieve

        The prompt:
        - Shows each snippet with its filename
        - Instructs the model to rely only on these snippets
        - Requires an explicit "I do not know" refusal when needed
        """

        if not snippets:
            return "I do not know based on the docs I have."

        context_blocks = []
        for filename, text in snippets:
            block = f"File: {filename}\n{text}\n"
            context_blocks.append(block)

        context = "\n\n".join(context_blocks)

        prompt = f"""
You are a cautious documentation assistant helping developers understand a codebase.

You will receive:
- A developer question
- A small set of snippets from project files

Your job:
- Answer the question using only the information in the snippets.
- If the snippets do not provide enough evidence, refuse to guess.

Snippets:
{context}

Developer question:
{query}

Rules:
- Use only the information in the snippets. Do not invent new functions,
  endpoints, or configuration values.
- If the snippets are not enough to answer confidently, reply exactly:
  "I do not know based on the docs I have."
- When you do answer, briefly mention which files you relied on.
"""

        response = self.model.generate_content(prompt)
        return (response.text or "").strip()

    def validate_grounded_answer(self, query, answer, snippets):
        """
        Ask Gemini to judge whether an answer is grounded in the provided snippets.

        Returns a dict with keys: score (0..1), is_grounded (bool), reason (str),
        or None if parsing fails.
        """
        if not snippets:
            return {
                "score": 0.0,
                "is_grounded": False,
                "reason": "No snippets were provided to validate against.",
            }

        context_blocks = []
        for filename, text in snippets:
            context_blocks.append(f"File: {filename}\n{text}\n")

        context = "\n\n".join(context_blocks)

        prompt = f"""
You are validating whether an AI answer is grounded in retrieved documentation.

Question:
{query}

Retrieved snippets:
{context}

Answer to validate:
{answer}

Respond with JSON only, with this exact schema:
{{
  "score": <number between 0 and 1>,
  "is_grounded": <true or false>,
  "reason": "<short explanation>"
}}

Scoring guidance:
- 1.0 means fully supported by snippets.
- 0.0 means not supported or contradicted by snippets.
- Mark is_grounded=false if the answer adds important claims not present in snippets.
"""

        response = self.model.generate_content(prompt)
        raw = (response.text or "").strip()
        return self._extract_json_object(raw)
