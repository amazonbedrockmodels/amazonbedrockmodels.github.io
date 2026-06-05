#!/usr/bin/env python3
"""
Find silently launched (beta) models by comparing models.json against
the AWS Bedrock docs model card pages (via the docs TOC).

A model is "beta" if its name doesn't fuzzy-match any model card title in the TOC.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

TOC_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide/toc-contents.json"
SUPPORTED_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html"

# AWS docs sits behind CloudFront/WAF that intermittently 403s datacenter IPs
# (e.g. GitHub Actions runners). Use a full browser-like header set and retry
# with backoff before giving up.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_RETRIES = 5


def _fetch_bytes(url):
    """Fetch a URL with browser headers, retrying transient failures (incl. 403)."""
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        req = Request(url, headers=_BROWSER_HEADERS)
        try:
            return urlopen(req, timeout=20).read()
        except (HTTPError, URLError) as e:
            last_err = e
            code = getattr(e, "code", None)
            # 403/429/5xx are transient WAF/CDN throttling — worth retrying.
            retryable = code in (403, 429) or (code is not None and code >= 500) or code is None
            if attempt < _MAX_RETRIES and retryable:
                wait = min(2 ** attempt, 30)
                print(f"  fetch {url} failed ({e}); retry {attempt}/{_MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            raise
    raise last_err


def fetch_json(url):
    return json.loads(_fetch_bytes(url))


def fetch_text(url):
    return _fetch_bytes(url).decode("utf-8", errors="replace")


def find_model_cards(node, parent_title="", results=None):
    """Extract (provider, title) pairs from TOC for model-card pages."""
    if results is None:
        results = []
    href = node.get("href", "")
    title = node.get("title", "")
    if "model-card-" in href:
        results.append((parent_title, title))
    for child in node.get("contents", []):
        find_model_cards(child, title or parent_title, results)
    return results


def normalize(s):
    """Normalize a name for fuzzy comparison: lowercase, strip release-date versions."""
    s = s.lower().strip()
    # Remove release-date version patterns like (24.07), (25.02)
    s = re.sub(r"\(\d{2}\.\d{2}\)", "", s)
    # Remove trailing version suffixes like v1, v2 (but not model-identity versions like 3.5)
    s = re.sub(r"\s+v\d+$", "", s)
    # Remove extra whitespace and normalize punctuation
    s = re.sub(r"[^a-z0-9. ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _prefix_match(shorter, longer):
    """Check if shorter is a word-boundary prefix of longer."""
    if not longer.startswith(shorter):
        return False
    # Must match at a word boundary (end of string, or next char is space)
    return len(longer) == len(shorter) or longer[len(shorter)] == " "


def is_fuzzy_match(model_name, toc_cards, provider):
    """Check if model_name fuzzy-matches any TOC title for the same provider."""
    norm_model = normalize(model_name)
    if not norm_model:
        return True

    provider_lower = provider.lower()
    for toc_provider, toc_title in toc_cards:
        if toc_provider.lower() != provider_lower:
            continue
        norm_toc = normalize(toc_title)
        # Exact match after normalization
        if norm_model == norm_toc:
            return True
        # One is a word-boundary prefix of the other
        if _prefix_match(norm_toc, norm_model) or _prefix_match(norm_model, norm_toc):
            return True
    return False


def load_models_json(filepath):
    with open(filepath) as f:
        return json.load(f)


def update_readme_table(beta_models, readme_path):
    rows = ["| Model Name | Model ID | Provider |", "|---|---|---|"]
    for m in sorted(beta_models, key=lambda x: (x["provider"], x["name"])):
        rows.append(f"| {m['name']} | {m['id']} | {m['provider']} |")
    table = "\n".join(rows)

    content = readme_path.read_text()
    begin, end = "<!-- BEGIN BETA_MODELS_TABLE -->", "<!-- END BETA_MODELS_TABLE -->"
    if begin not in content or end not in content:
        print("  Warning: markers not found in README")
        return
    content = re.sub(
        re.escape(begin) + r".*?" + re.escape(end),
        begin + "\n" + table + "\n" + end,
        content,
        flags=re.DOTALL,
    )
    readme_path.write_text(content)
    print(f"  Updated README table with {len(beta_models)} beta models")


def main():
    root = Path(__file__).parent.parent
    models_path = root / "data" / "models.json"
    output_path = root / "data" / "beta_models.json"
    readme_path = root / "README.md"

    print("Fetching docs TOC...")
    try:
        toc = fetch_json(TOC_URL)
        toc_cards = find_model_cards(toc)
        print(f"  Found {len(toc_cards)} model card pages")

        print("Fetching models-supported page...")
        supported_text = fetch_text(SUPPORTED_URL).lower()
        print(f"  Fetched {len(supported_text)} chars")
    except (HTTPError, URLError) as e:
        # AWS docs WAF blocked us even after retries. Beta detection is a
        # best-effort enrichment — don't fail the whole pipeline and lose the
        # already-refreshed main model data. Skip gracefully.
        print(f"\n  WARNING: could not fetch AWS docs ({e}); skipping beta model detection.")
        print("  Main model data is unaffected; leaving existing beta_models.json/README intact.")
        return

    print(f"\nLoading models from {models_path}...")
    models = load_models_json(models_path)

    # Deduplicate by model name + provider (many IDs share the same name)
    seen_names = set()
    beta_models = []
    found = 0

    for m in models:
        mid = m.get("modelId", "")
        name = m.get("modelName", "")
        provider = m.get("providerName", "")
        status = m.get("modelLifecycle", {}).get("status", "")
        if status == "LEGACY" or not mid:
            continue

        # Deduplicate: only check each unique (name, provider) once
        key = (name, provider)
        if key in seen_names:
            continue
        seen_names.add(key)

        # Check 1: fuzzy match against TOC model card titles
        if is_fuzzy_match(name, toc_cards, provider):
            found += 1
            continue

        # Check 2: model name appears on models-supported.html
        if name.lower() in supported_text:
            found += 1
            continue

        # Skip old models with no startOfLifeTime — they're deprecated, not beta
        sol = m.get("modelLifecycle", {}).get("startOfLifeTime")
        if not sol:
            found += 1
            continue

        # Skip models older than 1 year — not newly launched, just undocumented
        try:
            sol_str = str(sol).replace(" ", "T") if "T" not in str(sol) else str(sol)
            sol_dt = datetime.fromisoformat(sol_str)
            if sol_dt.tzinfo is None:
                sol_dt = sol_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - sol_dt > timedelta(days=365):
                found += 1
                continue
        except (ValueError, TypeError):
            pass

        beta_models.append({"id": mid, "name": name, "provider": provider})

    print(f"\nResults:")
    print(f"  Documented model names: {found}")
    print(f"  Beta models (undocumented): {len(beta_models)}")

    if beta_models:
        by_provider = defaultdict(list)
        for m in beta_models:
            by_provider[m["provider"]].append(m)
        for provider in sorted(by_provider):
            print(f"\n  {provider}:")
            for m in by_provider[provider]:
                print(f"    - {m['name']} ({m['id']})")

    print(f"\nSaving to {output_path}...")
    with open(output_path, "w") as f:
        json.dump(beta_models, f, indent=2)

    if readme_path.exists():
        print(f"Updating {readme_path}...")
        update_readme_table(beta_models, readme_path)


if __name__ == "__main__":
    main()
