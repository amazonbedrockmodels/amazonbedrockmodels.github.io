#!/usr/bin/env python3
"""
Fetch the authoritative set of models available on the bedrock-mantle endpoint.

The AWS docs model-card pages advertise mantle support, but they can be wrong
(preview models documented before they're actually deployed) and the HTML
layout changes without notice. The mantle endpoint exposes an OpenAI-compatible
`GET /v1/models` API that returns exactly what is live in each region — this is
ground truth.

Mantle is region-specific (e.g. openai.gpt-5.5 launched in us-east-2 only), so
this queries every mantle region and records per-region availability.

Auth: AWS SigV4 (service name "bedrock-mantle"). Uses standard credential
resolution — env vars (AWS_ACCESS_KEY_ID/SECRET) in CI, or --profile locally.

Output:
    data/mantle_models.json  - {"<modelId>": ["us-east-1", "us-east-2", ...], ...}
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
except ImportError:
    print("Error: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)

# Regions where the bedrock-mantle endpoint is available
# (https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html)
MANTLE_REGIONS = [
    "us-east-1", "us-east-2", "us-west-2",
    "ap-southeast-2", "ap-southeast-3", "ap-south-1", "ap-northeast-1",
    "eu-central-1", "eu-west-1", "eu-west-2", "eu-south-1", "eu-north-1",
    "sa-east-1",
]

SERVICE = "bedrock-mantle"


def list_mantle_models(creds, region: str) -> list:
    """Return [{"id", "created"}] for models live on bedrock-mantle in a region."""
    url = f"https://bedrock-mantle.{region}.api.aws/v1/models"
    req = AWSRequest(method="GET", url=url)
    SigV4Auth(creds, SERVICE, region).add_auth(req)
    http_req = urllib.request.Request(url, headers=dict(req.headers), method="GET")
    with urllib.request.urlopen(http_req, timeout=30) as resp:
        payload = json.loads(resp.read())
    return [{"id": m["id"], "created": m.get("created")} for m in payload.get("data", [])]


def main():
    parser = argparse.ArgumentParser(
        description="Fetch live bedrock-mantle model availability per region"
    )
    parser.add_argument("--profile", default=None, help="AWS profile (default: env creds)")
    parser.add_argument("--output", default="data/mantle_models.json")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    frozen = session.get_credentials()
    if frozen is None:
        print("Error: no AWS credentials found.")
        sys.exit(1)
    creds = frozen.get_frozen_credentials()

    by_model = {}  # modelId -> {"regions": [...], "created": <ts|None>}
    print("Querying bedrock-mantle /v1/models across regions...")
    for region in MANTLE_REGIONS:
        try:
            items = list_mantle_models(creds, region)
            for m in items:
                mid = m["id"]
                entry = by_model.setdefault(mid, {"regions": [], "created": None})
                entry["regions"].append(region)
                # created is identical across regions, but keep the earliest seen.
                c = m.get("created")
                if c is not None and (entry["created"] is None or c < entry["created"]):
                    entry["created"] = c
            print(f"  ✓ {region}: {len(items)} models")
        except urllib.error.HTTPError as e:
            # 403 in a region usually means mantle isn't enabled for this account
            # there yet — not fatal, just skip.
            print(f"  ⚠ {region}: HTTP {e.code} ({e.reason}) — skipping")
        except Exception as e:
            print(f"  ⚠ {region}: {type(e).__name__}: {e} — skipping")

    for mid in by_model:
        by_model[mid]["regions"] = sorted(by_model[mid]["regions"])

    if not by_model:
        print("Error: no mantle models returned from any region.")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(by_model, f, indent=2, sort_keys=True)
    print(f"\nSaved {len(by_model)} mantle models to {output_path}")


if __name__ == "__main__":
    main()
