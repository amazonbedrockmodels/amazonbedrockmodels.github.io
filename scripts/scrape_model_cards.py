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
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, List, Dict

BASE_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide"
TOC_URL = f"{BASE_URL}/toc-contents.json"
PRICING_URL = "https://aws.amazon.com/bedrock/pricing/"
# AWS docs sits behind CloudFront/WAF that intermittently 403s datacenter IPs
# (e.g. GitHub Actions runners). Use a full browser-like header set and retry.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_RETRIES = 4


class _PricingTableParser(HTMLParser):
    """Extract rows from the HTML tables on the Bedrock pricing page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and self._table is None:
            self._table = []
        elif self._table is not None and tag == "tr":
            self._row = []
        elif self._row is not None and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _normalize_model_name(value: str) -> str:
    """Normalize display names for matching pricing rows to model cards."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_pricing_page(html: str) -> dict:
    """Return on-demand token prices keyed by normalized model display name.

    AWS publishes several region-specific tables for a model. Keep the first
    price and mark it as region-dependent when another distinct price exists;
    this avoids presenting a single regional price as globally applicable.
    """
    parser = _PricingTableParser()
    parser.feed(html)
    prices = {}

    for rows in parser.tables:
        if not rows:
            continue
        headers = [cell.lower() for cell in rows[0]]
        input_index = next(
            (i for i, header in enumerate(headers)
             if re.search(r"price per (?:1m|1,000) input tokens", header)),
            None,
        )
        output_index = next(
            (i for i, header in enumerate(headers)
             if re.search(r"price per (?:1m|1,000) output tokens", header)),
            None,
        )
        if input_index is None or output_index is None:
            continue

        unit = "1M" if "1m" in headers[input_index] else "1,000"
        for row in rows[1:]:
            if len(row) <= max(input_index, output_index):
                continue
            model_name = _normalize_model_name(row[0])
            input_price = re.sub(r"\s+", "", row[input_index])
            output_price = re.sub(r"\s+", "", row[output_index])
            if not model_name or "$" not in input_price or "$" not in output_price:
                continue
            if "{priceof" in input_price.lower() or "{priceof" in output_price.lower():
                continue
            value = (
                f"Input: {input_price} / {unit} tokens; "
                f"Output: {output_price} / {unit} tokens"
            )
            prices.setdefault(model_name, [])
            if value not in prices[model_name]:
                prices[model_name].append(value)

    return {
        name: values[0] + (" (varies by region)" if len(values) > 1 else "")
        for name, values in prices.items()
    }


def fetch(url: str) -> str:
    """Fetch a URL with browser headers, retrying transient failures (incl. 403)."""
    from urllib.error import HTTPError, URLError

    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except (HTTPError, URLError) as e:
            last_err = e
            code = getattr(e, "code", None)
            retryable = code in (403, 429) or (code is not None and code >= 500) or code is None
            if attempt < _MAX_RETRIES and retryable:
                wait = min(2 ** attempt, 20)
                print(f"  fetch {url} failed ({e}); retry {attempt}/{_MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            raise
    raise last_err


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

    # Extract launch date. AWS now wraps the label in <b>…</b>, so allow up to
    # ~40 chars (closing tag + whitespace) between the label and the date.
    date_match = re.search(
        r"Model launch date:.{0,40}?([A-Za-z]{3,} \d{1,2}, \d{4})", html, re.S
    )
    if date_match:
        result["modelLaunchDate"] = date_match.group(1)

    # Extract EOL date
    eol_match = re.search(
        r"Model EOL date:.{0,40}?([A-Za-z]{3,} \d{1,2}, \d{4})", html, re.S
    )
    if eol_match:
        result["modelEolDate"] = eol_match.group(1)

    # Extract model limits. AWS currently renders these as plain text inside
    # <p> elements, but older cards used additional markup between the label
    # and value. Keep the gap bounded so a missing field cannot consume the
    # next model-detail field.
    limit_pattern = r"([0-9][0-9,]*(?:\.[0-9]+)?\s*[KMGTP]?)(?:\s+tokens?)?"
    context_match = re.search(
        rf"Context window:.{{0,80}}?{limit_pattern}", html, re.IGNORECASE | re.S
    )
    if context_match:
        result["contextWindow"] = f"{context_match.group(1).replace(' ', '')} tokens"

    output_match = re.search(
        rf"Max output tokens:.{{0,80}}?{limit_pattern}", html, re.IGNORECASE | re.S
    )
    if output_match:
        result["maxOutputTokens"] = f"{output_match.group(1).replace(' ', '')} tokens"

    # Older model cards included prices directly. Newer cards link to the
    # central Bedrock pricing page instead, so preserve the empty value when
    # no per-model price is present rather than accidentally scraping an
    # unrelated price from another section.
    pricing = {}
    price_matches = re.findall(
        r"Price per 1,000 tokens:.{0,80}?(\$\s*[0-9]+(?:\.[0-9]+)?(?:\s*[KMGTP])?)",
        html,
        re.IGNORECASE | re.S,
    )
    if price_matches:
        pricing["onDemand"] = ", ".join(re.sub(r"\s+", "", price) for price in price_matches)
    result["pricing"] = pricing

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

    # Extract model IDs mentioned on the page.
    # The <code> regex also catches code-sample filenames (e.g.
    # "bedrock-first-request.py"), so filter those out: real Bedrock model IDs
    # never end in a source-file extension.
    _FILE_EXT = (
        ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml",
        ".md", ".txt", ".html", ".htm", ".csv", ".cfg", ".ini",
    )
    raw_ids = re.findall(
        r'<code[^>]*>([a-z][a-z0-9-]+\.[a-z][a-z0-9._:-]+)</code>', html
    )
    model_ids = [
        mid for mid in raw_ids
        if not mid.lower().endswith(_FILE_EXT) and "/" not in mid
    ]
    if model_ids:
        result["modelIds"] = sorted(set(model_ids))

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


def _check_support(html: str, item_name: str) -> Optional[bool]:
    """Check if an API/endpoint is supported on a model card page.

    The current AWS docs layout renders each capability as a status icon
    immediately followed by the name in a <code> tag, e.g.:
        <img src=".../icon-yes.png" alt="Green circle..."/><code class="code">Converse</code>
        <img src=".../icon-no.png"  alt="Red circle..."/><code class="code">Invoke</code>
    The icon filename (icon-yes / icon-no) is the reliable signal.
    """
    esc = re.escape(item_name)

    # Current layout: <img src="...icon-(yes|no).png" ...><code ...>NAME</code>
    m = re.search(
        rf'icon-(yes|no)\.png"[^<]*?/?>\s*<code[^>]*>\s*{esc}\s*</code>',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).lower() == "yes"

    # Legacy fallback: alt="Yes|No" near the item name (either order).
    m = re.search(
        rf'alt="(Yes|No)"[^>]*>[^<]*(?:<[^>]*>)*[^<]*{esc}', html, re.IGNORECASE
    )
    if m:
        return m.group(1).lower() == "yes"
    m = re.search(
        rf'{esc}[^<]*(?:<[^>]*>)*[^<]*alt="(Yes|No)"', html, re.IGNORECASE
    )
    if m:
        return m.group(1).lower() == "yes"

    return None


def apply_mantle_overrides(cards: dict, mantle_by_model: dict) -> int:
    """Correct each card's bedrockMantle flag using live /v1/models truth.

    The docs model-card pages can advertise mantle support before a model is
    actually deployed (e.g. preview models), and the HTML can be stale. The
    live mantle endpoint is ground truth, so we override:
      - endpointsSupported.bedrockMantle = whether any of the card's modelIds
        is live on mantle in at least one region
      - mantleRegions = sorted union of regions where it's live
      - mantleCreated = earliest /v1/models `created` timestamp across the
        card's modelIds (a reliable launch date, esp. for mantle-only models)

    mantle_by_model maps modelId -> {"regions": [...], "created": <ts|None>}.

    Returns the number of cards whose bedrockMantle flag was corrected.
    """
    corrected = 0
    for card in cards.values():
        meta = card.get("metadata", {})
        if not meta or "error" in meta:
            continue
        ids = meta.get("modelIds", [])
        regions = set()
        created = None
        for mid in ids:
            info = mantle_by_model.get(mid)
            if not info:
                continue
            regions.update(info.get("regions", []))
            c = info.get("created")
            if c is not None and (created is None or c < created):
                created = c
        live = bool(regions)
        eps = meta.setdefault("endpointsSupported", {})
        if eps.get("bedrockMantle") != live:
            corrected += 1
        eps["bedrockMantle"] = live
        meta["mantleRegions"] = sorted(regions)
        if created is not None:
            meta["mantleCreated"] = created
    return corrected


def match_cards_to_models(
    cards_data: dict, models: list, pricing_by_model: Optional[dict] = None
) -> dict:
    """Match scraped model card data to model IDs in models.json.

    Also matches variant model IDs (e.g. amazon.nova-pro-v1:0:256k)
    by stripping the suffix after the second ':' delimiter.
    """
    pricing_by_model = pricing_by_model or {}
    enriched = {}

    for slug, card_info in cards_data.items():
        card_meta = card_info.get("metadata", {})
        model_ids = card_meta.get("modelIds", [])

        for mid in model_ids:
            card_data = {
                "modelLaunchDate": card_meta.get("modelLaunchDate"),
                "modelEolDate": card_meta.get("modelEolDate"),
                "contextWindow": card_meta.get("contextWindow"),
                "maxOutputTokens": card_meta.get("maxOutputTokens"),
                "apisSupported": card_meta.get("apisSupported", {}),
                "endpointsSupported": card_meta.get("endpointsSupported", {}),
                "mantleRegions": card_meta.get("mantleRegions", []),
                "pricing": card_meta.get("pricing", {}),
                "modelCardUrl": card_info.get("url", ""),
            }
            enriched[mid] = card_data

    # Also map variant model IDs (with double : suffix like :256k, :mm)
    # by looking up the base model ID (everything before the second :).
    for model in models:
        mid = model.get("modelId", "")
        if mid not in enriched:
            parts = mid.split(":")
            if len(parts) >= 3:
                base_id = ":".join(parts[:2])
                if base_id in enriched:
                    enriched[mid] = enriched[base_id]

    # Pricing is keyed by the display name in AWS's pricing tables rather than
    # by Bedrock model ID. Apply it after variant expansion so every matching
    # model receives the same metadata.
    for model in models:
        mid = model.get("modelId", "")
        card_data = enriched.get(mid)
        if not card_data or card_data.get("pricing", {}).get("onDemand"):
            continue
        price = pricing_by_model.get(_normalize_model_name(model.get("modelName", "")))
        if price:
            card_data["pricing"] = {"onDemand": price}

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
    parser.add_argument(
        "--mantle-file",
        default="data/mantle_models.json",
        help="Live mantle availability JSON from fetch_mantle_models.py "
        "(default: data/mantle_models.json). Used to correct bedrockMantle "
        "flags with ground truth; skipped gracefully if missing.",
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

    # AWS moved model pricing from individual model cards to the central
    # pricing page. A pricing fetch failure must not discard the model-card
    # metadata, so keep this enrichment best-effort.
    pricing_by_model = {}
    try:
        pricing_by_model = parse_pricing_page(fetch(PRICING_URL))
        print(f"\nParsed pricing for {len(pricing_by_model)} model names")
    except Exception as e:
        print(f"\nPricing fetch failed: {e}; continuing without pricing enrichment")

    # Correct bedrockMantle flags using live /v1/models truth (ground truth).
    mantle_path = Path(args.mantle_file)
    if mantle_path.exists():
        with open(mantle_path) as f:
            mantle_by_model = json.load(f)
        corrected = apply_mantle_overrides(cards, mantle_by_model)
        print(
            f"\nApplied live mantle availability from {mantle_path} "
            f"({len(mantle_by_model)} live models; corrected {corrected} card flags)"
        )
    else:
        print(
            f"\nNote: {mantle_path} not found — keeping scraped bedrockMantle "
            "flags as-is (run scripts/fetch_mantle_models.py to get live truth)."
        )

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

            enriched = match_cards_to_models(cards, models, pricing_by_model)
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
