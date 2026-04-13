"""Utilities for loading external documentation sources with local caching."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_CACHE_DIR = ".doc_cache"
DEFAULT_TIMEOUT_SECONDS = 12


def _url_to_cache_name(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.json"


def _strip_html(raw_html: str) -> str:
    # Remove script/style blocks first to reduce noise.
    no_scripts = re.sub(
        r"<script[\\s\\S]*?</script>|<style[\\s\\S]*?</style>",
        " ",
        raw_html,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", no_scripts)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_url_text(url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "DocuBot/1.0 (+https://example.local)",
            "Accept": "text/html, text/plain, text/markdown",
        },
    )

    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read().decode("utf-8", errors="replace")

    if "html" in content_type.lower() or "<html" in body.lower():
        return _strip_html(body)
    return body.strip()


def _load_cache(cache_path: str):
    if not os.path.exists(cache_path):
        return None
    with open(cache_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("text")


def _save_cache(cache_path: str, url: str, text: str):
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    payload = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "text": text,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_external_documents(
    urls,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
):
    """
    Fetches external docs and returns list of (filename, text).

    For reproducibility, successful fetches are cached under cache_dir.
    If fetching fails and a cache entry exists, cached content is returned.
    """
    documents = []
    failures = []

    for url in urls or []:
        url = (url or "").strip()
        if not url:
            continue

        cache_name = _url_to_cache_name(url)
        cache_path = os.path.join(cache_dir, cache_name)
        filename = f"REMOTE::{cache_name}"

        try:
            text = _fetch_url_text(url)
            if not text:
                raise RuntimeError("Downloaded empty document")
            if use_cache:
                _save_cache(cache_path, url, text)
            documents.append((filename, text))
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            cached = _load_cache(cache_path) if use_cache else None
            if cached:
                documents.append((filename, cached))
            else:
                failures.append((url, str(exc)))

    return documents, failures