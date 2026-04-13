# Setup Guide

This guide is for running DocuBot and the extension features (External RAG + validation) with minimal setup.

## Requirements
- Python 3.9+
- `pip`
- Gemini API key for LLM features

## 1. Install dependencies
From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure environment variables
Create your env file:

```bash
cp .env.example .env
```

Set at least:

```bash
GEMINI_API_KEY=your_api_key_here
```

Optional extension settings:

```bash
EXTERNAL_DOC_URLS=https://example.com/docs,https://example.com/api
VALIDATION_MIN_SCORE=0.65
DOCUBOT_LOG_PATH=logs/external_rag_runs.jsonl
```

Recommended starter set for better evidence coverage in validated mode:

```bash
EXTERNAL_DOC_URLS=https://raw.githubusercontent.com/tiangolo/fastapi/master/docs/en/docs/tutorial/security/oauth2-jwt.md,https://raw.githubusercontent.com/tiangolo/fastapi/master/docs/en/docs/tutorial/sql-databases.md,https://raw.githubusercontent.com/tiangolo/fastapi/master/docs/en/docs/tutorial/path-params.md
```

## 3. Run DocuBot

```bash
python main.py
```

Mode summary:
- `1` Naive LLM over full docs
- `2` Retrieval only
- `3` RAG
- `4` External RAG + hard validation

## 4. Run evaluations
Baseline retrieval:

```bash
python evaluation.py
```

Validated extension evaluation:

```bash
python evaluation.py --validated-external-rag
```

This prints:
- groundedness pass rate
- per-query validation method/score
- block reason summary

## 5. Troubleshooting
- If mode 1/3/4 are unavailable, check `GEMINI_API_KEY`.
- If mode 4 refuses too often, lower `VALIDATION_MIN_SCORE` slightly.
- If external docs do not load, verify URL accessibility and check cached data in `.doc_cache/`.
