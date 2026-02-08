#!/usr/bin/env python3
"""
Refresh Bedrock Models and Inference Profiles Data

This script dynamically discovers all AWS regions supporting Amazon Bedrock,
fetches foundation models and inference profiles from each region, deduplicates
models with per-region availability tracking, and outputs JSON files.

Usage:
    python scripts/refresh-bedrock-data.py

AWS Credentials:
    Uses AWS credentials from environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    Or from default AWS configuration (~/.aws/credentials)

Output:
    data/models.json    - Deduplicated foundation models with region availability
    data/profiles.json  - Inference profiles with region field
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import argparse

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    print("Error: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)


class BedrockDataCollector:
    """Collects Bedrock models and profiles from all available regions."""

    def __init__(self, profile_name: str = "default"):
        """Initialize with AWS profile or environment variables."""
        self.profile_name = profile_name
        # In GitHub Actions, AWS credentials are provided via environment variables
        # If profile_name is 'default' and env vars are set, use env vars
        import os
        if profile_name == "default" and os.getenv("AWS_ACCESS_KEY_ID"):
            self.session = boto3.Session()
        else:
            self.session = boto3.Session(profile_name=profile_name)
        self.supported_regions = []
        self.models_by_id = {}  # For deduplication
        self.profiles_list = []

    def discover_bedrock_regions(self) -> List[str]:
        """
        Discover all AWS regions that support Amazon Bedrock.

        Attempts to list foundation models in each region. If successful,
        the region supports Bedrock.
        """
        print("Discovering Bedrock-supported regions...")
        ec2_client = self.session.client("ec2", region_name="us-east-1")

        try:
            regions_response = ec2_client.describe_regions()
            all_regions = [r["RegionName"] for r in regions_response["Regions"]]
        except (BotoCoreError, ClientError) as e:
            print(f"Error fetching regions: {e}")
            raise

        supported = []
        for region in all_regions:
            try:
                bedrock_client = self.session.client("bedrock", region_name=region)
                response = bedrock_client.list_foundation_models()
                # If we get a successful response, the region supports Bedrock
                if "modelSummaries" in response:
                    supported.append(region)
                    print(f"  ✓ {region}")
            except (BotoCoreError, ClientError):
                # Region does not support Bedrock
                pass
            except Exception as e:
                # Unexpected error - log and continue
                print(f"  ⚠ {region}: Unexpected error: {e}")

        self.supported_regions = supported
        print(f"Found {len(supported)} regions supporting Bedrock\n")
        return supported

    def fetch_models_from_region(self, region: str) -> List[Dict[str, Any]]:
        """Fetch all foundation models from a specific region."""
        bedrock_client = self.session.client("bedrock", region_name=region)

        try:
            response = bedrock_client.list_foundation_models()
            models = response.get("modelSummaries", [])
            print(f"  Fetched {len(models)} models from {region}")
            return models
        except (BotoCoreError, ClientError) as e:
            print(f"  Error fetching models from {region}: {e}")
            raise

    def fetch_profiles_from_region(self, region: str) -> List[Dict[str, Any]]:
        """Fetch all inference profiles from a specific region."""
        bedrock_client = self.session.client("bedrock", region_name=region)

        try:
            response = bedrock_client.list_inference_profiles()
            profiles = response.get("inferenceProfileSummaries", [])
            print(f"  Fetched {len(profiles)} profiles from {region}")
            return profiles
        except (BotoCoreError, ClientError) as e:
            print(f"  Error fetching profiles from {region}: {e}")
            raise

    def deduplicate_and_collect_models(self):
        """Fetch models from all regions and deduplicate by modelId."""
        print("Collecting models from all regions...")
        for region in self.supported_regions:
            try:
                models = self.fetch_models_from_region(region)
                for model in models:
                    model_id = model.get("modelId")
                    if not model_id:
                        continue

                    if model_id not in self.models_by_id:
                        # First time seeing this model
                        self.models_by_id[model_id] = model.copy()
                        self.models_by_id[model_id]["regions"] = [region]
                    else:
                        # Add region to existing model
                        if region not in self.models_by_id[model_id]["regions"]:
                            self.models_by_id[model_id]["regions"].append(region)
            except (BotoCoreError, ClientError, Exception) as e:
                print(f"  Error processing region {region}: {e}")
                raise

        print(f"Deduplicated to {len(self.models_by_id)} unique models\n")

    def collect_and_flatten_profiles(self):
        """Fetch profiles from all regions and flatten with region field."""
        print("Collecting profiles from all regions...")
        for region in self.supported_regions:
            try:
                profiles = self.fetch_profiles_from_region(region)
                for profile in profiles:
                    profile_copy = profile.copy()
                    profile_copy["region"] = region
                    self.profiles_list.append(profile_copy)
            except (BotoCoreError, ClientError, Exception) as e:
                print(f"  Error processing region {region}: {e}")
                raise

        print(f"Collected {len(self.profiles_list)} profiles total\n")

    def save_data(self, output_dir: str = "data"):
        """Save models and profiles to JSON files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save models
        models_file = output_path / "models.json"
        models_data = list(self.models_by_id.values())
        with open(models_file, "w") as f:
            json.dump(models_data, f, indent=2, default=str)
        print(f"Saved {len(models_data)} models to {models_file}")

        # Save profiles
        profiles_file = output_path / "profiles.json"
        with open(profiles_file, "w") as f:
            json.dump(self.profiles_list, f, indent=2, default=str)
        print(f"Saved {len(self.profiles_list)} profiles to {profiles_file}")

    def run(self, output_dir: str = "data"):
        """Execute the full data collection and save process."""
        try:
            self.discover_bedrock_regions()
            if not self.supported_regions:
                print("Error: No Bedrock-supported regions found!")
                sys.exit(1)

            self.deduplicate_and_collect_models()
            self.collect_and_flatten_profiles()
            self.save_data(output_dir)
            print("\n✓ Data refresh completed successfully!")
        except Exception as e:
            print(f"\n✗ Data refresh failed: {e}")
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Refresh Amazon Bedrock models and profiles data"
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="AWS profile to use (default: 'default')",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Output directory for JSON files (default: 'data')",
    )

    args = parser.parse_args()

    collector = BedrockDataCollector(profile_name=args.profile)
    collector.run(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
