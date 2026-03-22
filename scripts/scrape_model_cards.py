#!/usr/bin/env python3
"""
Scrape AWS Bedrock model card pages for API/endpoint support metadata.

Enriches models.json with:
  - modelLaunchDate
  - apisSupported: {responses, chatCompletions, invoke, converse}
  - endpointsSupported: {bedrockRuntime, bedrockMantle}

Usage:
    python scripts/scrape_model_cards.py [--output data/model_cards.json]
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict

BASE_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide"
TOC_URL = f"{BASE_URL}/toc-contents.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BedrockModelCatalog/1.0)"}


def fetch(url: str) -> str:
    """Fetch a URL and return the response text."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def discover_model_card_urls() -> Dict[str, str]:
    """Discover all model card page URLs from the TOC or by pattern matching."""
    print("Discovering model card pages...")
    try:
        toc_json = fetch(TOC_URL)
        toc = json.loads(toc_json)
        cards = {}
        _walk_toc(toc, cards)
        print(f"  Found {len(cards)} model card pages from TOC")
        return cards
    except Exception as e:
        print(f"  TOC fetch failed: {e}, falling back to models-supported page")
        return discover_from_supported_page()


def _walk_toc(node, cards: dict):
    """Recursively walk TOC JSON to find model-card entries."""
    if isinstance(node, dict):
        href = node.get("href", "")
        title = node.get("title", "")
        if "model-card-" in href:
            slug = href.replace(".html", "").replace("model-card-", "")
            cards[slug] = {"url": f"{BASE_URL}/{href}", "title": title}
        for child in node.get("contents", []):
            _walk_toc(child, cards)
    elif isinstance(node, list):
        for item in node:
            _walk_toc(item, cards)


def discover_from_supported_page() -> dict[str, str]:
    """Fallback: scrape models-supported.html for model card links."""
    html = fetch(f"{BASE_URL}/models-supported.html")
    links = re.findall(r'href="(model-card-[^"]+\.html)"', html)
    cards = {}
    for link in links:
        slug = link.replace(".html", "").replace("model-card-", "")
        cards[slug] = {"url": f"{BASE_URL}/{link}", "title": slug}
    return cards


def parse_model_card(html: str) -> dict:
    """Parse a model card HTML page for metadata."""
    result = {}

    # Extract launch date
    date_match = re.search(r"Model launch date:\s*([A-Za-z]+ \d{1,2}, \d{4})", html)
    if date_match:
        result["modelLaunchDate"] = date_match.group(1)

    # Extract EOL date
    eol_match = re.search(r"Model EOL date:\s*([A-Za-z]+ \d{1,2}, \d{4})", html)
    if eol_match:
        result["modelEolDate"] = eol_match.group(1)

    # Extract APIs supported — search full HTML (section extraction too narrow)
    result["apisSupported"] = {}
    for api_name, key in [
        ("Responses", "responses"),
        ("Chat Completions", "chatCompletions"),
        ("Invoke", "invoke"),
        ("Converse", "converse"),
    ]:
        supported = _check_support(html, api_name)
        if supported is not None:
            result["apisSupported"][key] = supported

    # Extract Endpoints supported — search full HTML
    result["endpointsSupported"] = {}
    for ep_name, key in [
        ("bedrock-runtime", "bedrockRuntime"),
        ("bedrock-mantle", "bedrockMantle"),
    ]:
        supported = _check_support(html, ep_name)
        if supported is not None:
            result["endpointsSupported"][key] = supported

    # Extract model IDs mentioned on the page
    model_ids = re.findall(
        r'<code[^>]*>([a-z][a-z0-9-]+\.[a-z][a-z0-9._:-]+)</code>', html
    )
    if model_ids:
        result["modelIds"] = list(set(model_ids))

    return result


def _extract_section(html: str, section_name: str) -> Optional[str]:
    """Extract HTML content around a section heading."""
    # Find the section by looking for bold/heading text
    pattern = rf">{section_name}</(?:b|strong|h\d)"
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        # Try without closing tag
        pattern = rf">\s*{section_name}\s*<"
        match = re.search(pattern, html, re.IGNORECASE)
    if match:
        # Get ~2000 chars after the match for the section content
        start = match.start()
        return html[start : start + 2000]
    return None


def _check_support(section_html: str, item_name: str) -> Optional[bool]:
    """Check if an item is supported (Yes/No icon) in a section."""
    # Look for the pattern: alt="Yes|No" ... item_name
    # The icon appears before the text
    pattern = rf'alt="(Yes|No)"[^>]*>[^<]*(?:<[^>]*>)*[^<]*{re.escape(item_name)}'
    match = re.search(pattern, section_html, re.IGNORECASE)
    if match:
        return match.group(1) == "Yes"

    # Try reverse: item_name ... alt="Yes|No"
    pattern = rf'{re.escape(item_name)}[^<]*(?:<[^>]*>)*[^<]*alt="(Yes|No)"'
    match = re.search(pattern, section_html, re.IGNORECASE)
    if match:
        return match.group(1) == "Yes"

    return None


def match_cards_to_models(
    cards_data: dict, models: list
) -> dict:
    """Match scraped model card data to model IDs in models.json."""
    # Build a lookup from model ID to card data
    enriched = {}

    for slug, card_info in cards_data.items():
        card_meta = card_info.get("metadata", {})
        model_ids = card_meta.get("modelIds", [])

        for mid in model_ids:
            enriched[mid] = {
                "modelLaunchDate": card_meta.get("modelLaunchDate"),
                "modelEolDate": card_meta.get("modelEolDate"),
                "apisSupported": card_meta.get("apisSupported", {}),
                "endpointsSupported": card_meta.get("endpointsSupported", {}),
                "modelCardUrl": card_info.get("url", ""),
            }

    return enriched


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Bedrock model card pages")
    parser.add_argument(
        "--output",
        default="data/model_cards.json",
        help="Output file (default: data/model_cards.json)",
    )
    parser.add_argument(
        "--enrich-models",
        action="store_true",
        help="Also enrich data/models.json with scraped data",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    args = parser.parse_args()

    # Discover model card pages
    cards = discover_model_card_urls()
    if not cards:
        print("No model card pages found!")
        sys.exit(1)

    # Scrape each model card page
    print(f"\nScraping {len(cards)} model card pages...")
    for i, (slug, info) in enumerate(cards.items()):
        url = info["url"]
        try:
            html = fetch(url)
            metadata = parse_model_card(html)
            cards[slug]["metadata"] = metadata
            apis = metadata.get("apisSupported", {})
            eps = metadata.get("endpointsSupported", {})
            date = metadata.get("modelLaunchDate", "?")
            print(
                f"  [{i+1}/{len(cards)}] {slug}: "
                f"date={date}, "
                f"apis={apis}, "
                f"endpoints={eps}, "
                f"modelIds={len(metadata.get('modelIds', []))}"
            )
        except Exception as e:
            print(f"  [{i+1}/{len(cards)}] {slug}: ERROR {e}")
            cards[slug]["metadata"] = {"error": str(e)}

        if args.delay > 0:
            time.sleep(args.delay)

    # Save raw card data
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(cards, f, indent=2)
    print(f"\nSaved {len(cards)} model cards to {output_path}")

    # Optionally enrich models.json
    if args.enrich_models:
        models_path = Path("data/models.json")
        if models_path.exists():
            with open(models_path) as f:
                models = json.load(f)

            enriched = match_cards_to_models(cards, models)
            enriched_count = 0
            for model in models:
                mid = model.get("modelId", "")
                if mid in enriched:
                    model["modelCard"] = enriched[mid]
                    enriched_count += 1

            with open(models_path, "w") as f:
                json.dump(models, f, indent=2, default=str)
            print(f"Enriched {enriched_count}/{len(models)} models in {models_path}")
        else:
            print(f"Warning: {models_path} not found, skipping enrichment")

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
