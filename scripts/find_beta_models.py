#!/usr/bin/env python3
"""
Find silently launched (beta) models by comparing models.json against
pricing tables from AWS Bedrock pricing page.

A model is considered "beta" if it appears in models.json but NOT in the pricing table.
"""

import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict
from difflib import SequenceMatcher

def load_models_json(filepath):
    """Load and parse models.json"""
    with open(filepath, 'r') as f:
        models = json.load(f)

    # Extract model IDs and names
    model_info = {}
    for model in models:
        model_id = model.get('modelId', '')
        model_name = model.get('modelName', '')
        provider = model.get('providerName', '')

        if model_id:
            model_info[model_id] = {
                'name': model_name,
                'provider': provider,
                'full_model': model
            }

    return model_info

def normalize_model_name(name):
    """Normalize model names for comparison"""
    if not name:
        return ""
    return name.lower().strip()

def extract_pricing_html_content(html_filepath):
    """Extract raw HTML content and return as decoded plaintext"""
    with open(html_filepath, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Decode HTML entities
    html_content = html.unescape(html_content)

    return html_content

def find_beta_models(models_data, html_content):
    """
    Find models that appear in models.json but not in the pricing HTML.

    Uses plaintext search for exact matches in the HTML content.
    Excludes LEGACY models from the beta list.
    """

    beta_models = []
    found_models = []

    for model_id, model_info in models_data.items():
        model_name = model_info['name']
        provider = model_info['provider']
        full_model = model_info['full_model']

        # Skip LEGACY models
        lifecycle_status = full_model.get('modelLifecycle', {}).get('status', '')
        if lifecycle_status == 'LEGACY':
            continue

        # Direct plaintext search in HTML
        # Try exact match first
        if model_name in html_content:
            found_models.append({
                'id': model_id,
                'name': model_name,
                'provider': provider
            })
        else:
            # Try case-insensitive search
            if model_name.lower() in html_content.lower():
                found_models.append({
                    'id': model_id,
                    'name': model_name,
                    'provider': provider
                })
            else:
                beta_models.append({
                    'id': model_id,
                    'name': model_name,
                    'provider': provider
                })

    return beta_models, found_models

def update_readme_table(beta_models, readme_path):
    """Update the markdown table in README.md with beta models"""
    # Generate markdown table
    table_rows = ["| Model Name | Model ID | Provider |"]
    table_rows.append("|---|---|---|")

    # Sort by provider then name
    sorted_models = sorted(beta_models, key=lambda x: (x['provider'], x['name']))
    for model in sorted_models:
        table_rows.append(f"| {model['name']} | {model['id']} | {model['provider']} |")

    markdown_table = "\n".join(table_rows)

    # Read README
    with open(readme_path, 'r', encoding='utf-8') as f:
        readme_content = f.read()

    # Find and replace content between markers
    begin_marker = "<!-- BEGIN BETA_MODELS_TABLE -->"
    end_marker = "<!-- END BETA_MODELS_TABLE -->"

    if begin_marker not in readme_content or end_marker not in readme_content:
        print(f"  Warning: Markers not found in {readme_path}")
        return

    # Replace table content
    import re
    pattern = re.compile(
        re.escape(begin_marker) + r'.*?' + re.escape(end_marker),
        re.DOTALL
    )
    new_content = pattern.sub(
        begin_marker + '\n' + markdown_table + '\n' + end_marker,
        readme_content
    )

    # Write back
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"  Updated README table with {len(sorted_models)} beta models")

def main():
    workspace_root = Path(__file__).parent.parent
    models_json_path = workspace_root / 'data' / 'models.json'
    # Use the models-regions page instead of pricing
    html_path = workspace_root / 'temp' / 'bedrock-models-regions.html'
    output_path = workspace_root / 'data' / 'beta_models.json'

    print(f"Loading models from {models_json_path}...")
    models_data = load_models_json(models_json_path)
    print(f"  Found {len(models_data)} total models")

    print(f"\nExtracting model content from {html_path}...")
    if not html_path.exists():
        print(f"  ERROR: HTML file not found at {html_path}")
        return

    html_content = extract_pricing_html_content(html_path)
    print(f"  Decoded HTML content: {len(html_content)} characters")

    print(f"\nFinding beta models...")
    beta_models, found_models = find_beta_models(models_data, html_content)

    print(f"\nResults:")
    print(f"  Models in pricing table: {len(found_models)}")
    print(f"  Models NOT in pricing table (beta): {len(beta_models)}")

    if beta_models:
        print(f"\nBeta Models Found ({len(beta_models)}):")
        # Group by provider
        by_provider = defaultdict(list)
        for model in beta_models:
            by_provider[model['provider']].append(model)

        for provider in sorted(by_provider.keys()):
            print(f"\n  {provider}:")
            for model in by_provider[provider]:
                print(f"    - {model['name']} ({model['id']})")

    # Save beta models to JSON
    print(f"\nSaving beta models to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(beta_models, f, indent=2)
    print(f"  Saved {len(beta_models)} beta models")

    # Update README with markdown table
    readme_path = workspace_root / 'README.md'
    if readme_path.exists():
        print(f"\nUpdating {readme_path}...")
        update_readme_table(beta_models, readme_path)
    else:
        print(f"  Warning: README.md not found at {readme_path}")

if __name__ == '__main__':
    main()
