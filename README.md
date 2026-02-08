# Amazon Bedrock Models

An interactive, filterable table of all available Amazon Bedrock foundation models and inference profiles. This project keeps models up-to-date with daily automated refreshes from AWS Bedrock APIs.

**Live Site:** Will be deployed to `https://amazonbedrockmodels.github.io`

## Silently Launched (Beta) Models

<!-- BEGIN BETA_MODELS_TABLE -->
| Model Name | Model ID | Provider |
|---|---|---|
| DeepSeek V3.2 | deepseek.v3.2 | DeepSeek |
| MiniMax M2.1 | minimax.minimax-m2.1 | MiniMax |
| Kimi K2.5 | moonshotai.kimi-k2.5 | Moonshot AI |
| Nemotron Nano 3 30B | nvidia.nemotron-nano-3-30b | NVIDIA |
| Qwen3 Coder Next | qwen.qwen3-coder-next | Qwen |
| GLM 4.7 | zai.glm-4.7 | Z.AI |
| GLM 4.7 Flash | zai.glm-4.7-flash | Z.AI |
<!-- END BETA_MODELS_TABLE -->

## Why This Project?

The official AWS documentation can lag behind the actual available models and regions. This site provides:
- **Real-time data**: Fetched directly from AWS Bedrock APIs
- **Daily updates**: Automated refresh every 24 hours
- **Interactive filtering**: Search, filter by provider, modality, region, and status
- **Inference profiles**: Copy-to-clipboard modal showing available profiles per model
- **Region tracking**: See which regions support each model

## Features

✨ **Interactive Table**
- Sort by Model ID, Name, or Provider
- Filter by provider, status, region, and input/output modalities
- Full-text search across model IDs and names
- Responsive design for mobile and desktop

🔍 **Inference Profiles**
- View available inference profiles per model in a modal
- Copy profile IDs with one click
- Region and status information for each profile

📊 **Comprehensive Data**
- All foundation models across all Bedrock-supported regions
- Input/output modalities (TEXT, IMAGE, EMBEDDING)
- Model lifecycle status (ACTIVE, LEGACY)
- Streaming support indicators
- Customization and inference type support

🔄 **Automated Updates**
- Daily scheduled GitHub Actions workflow
- Dynamic region discovery (no hardcoded lists)
- Deduplication with per-region availability tracking

## Project Structure

```
amazonbedrockmodels/
├── index.html                           # Main HTML page
├── css/
│   └── styles.css                       # Styling and responsive design
├── js/
│   └── app.js                           # Frontend logic (filtering, rendering, modal)
├── scripts/
│   └── refresh-bedrock-data.py          # Python script to fetch and deduplicate data
├── data/
│   ├── models.json                      # Deduplicated foundation models with regions
│   └── profiles.json                    # Inference profiles with region field
├── .github/
│   └── workflows/
│       └── update-bedrock-data.yml      # GitHub Actions daily update workflow
├── .gitignore                           # Ignore AWS credentials, etc.
└── README.md                            # This file
```

## Data Structure

### models.json

Array of deduplicated foundation models with per-region availability:

```json
[
  {
    "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0:18k",
    "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0:18k",
    "modelName": "Claude 3.5 Sonnet v2",
    "providerName": "Anthropic",
    "inputModalities": ["TEXT", "IMAGE"],
    "outputModalities": ["TEXT"],
    "responseStreamingSupported": true,
    "customizationsSupported": [],
    "inferenceTypesSupported": ["PROVISIONED"],
    "modelLifecycle": {
      "status": "ACTIVE"
    },
    "regions": ["us-east-1", "us-west-2", "eu-west-1"]
  }
]
```

### profiles.json

Array of inference profiles with region field:

```json
[
  {
    "inferenceProfileName": "claude-3-5-sonnet-us-west-2",
    "description": "Claude 3.5 Sonnet for US West 2",
    "createdAt": "2024-10-22T00:00:00.000Z",
    "updatedAt": "2024-10-22T00:00:00.000Z",
    "inferenceProfileArn": "arn:aws:bedrock:us-west-2::inference-profile/anthropic.claude-3-5-sonnet-20241022-v2:0:18k",
    "inferenceProfileId": "anthropic.claude-3-5-sonnet-20241022-v2:0:18k-us-west-2",
    "status": "ACTIVE",
    "type": "SYSTEM_DEFINED",
    "models": [
      "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0:18k"
    ],
    "region": "us-west-2"
  }
]
```

## Local Setup

### Prerequisites

- Python 3.8+
- AWS credentials configured locally with Bedrock permissions
- Git (for local development)

### Installation

1. **Clone the repository** (when deployed):
   ```bash
   git clone https://github.com/amazonbedrockmodels/amazonbedrockmodels.github.io.git
   cd amazonbedrockmodels
   ```

2. **Install Python dependencies**:
   ```bash
   pip install boto3
   ```

3. **Configure AWS credentials** via environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1
   ```

### Running the Data Refresh Script

To fetch the latest models and profiles:

```bash
# Using the default AWS profile
python scripts/refresh-bedrock-data.py

# Specify custom output directory
python scripts/refresh-bedrock-data.py --output-dir custom_data
```

The script will:
1. Discover all AWS regions supporting Bedrock
2. Fetch foundation models and inference profiles from each region
3. Deduplicate models by ID, tracking available regions
4. Output `data/models.json` and `data/profiles.json`

**Error Handling**: The script uses a "fail-fast" approach. If an error occurs during region discovery or data fetching, the script will exit with an error message. The next scheduled run will retry.

### Viewing Locally

1. **Start a local web server**:
   ```bash
   # Python 3
   python -m http.server 8000

   # Or use any other local server (Live Server, etc.)
   ```

2. **Open in browser**:
   ```
   http://localhost:8000
   ```

3. **Interact with the page**:
   - Use filter dropdowns and search
   - Click "View Profiles" to see inference profiles
   - Click "Copy" to copy profile IDs to clipboard

## Filtering Features

- **Search**: Full-text search across model IDs and names
- **Provider**: Filter by model provider (Anthropic, Meta, Mistral, etc.)
- **Status**: Show ACTIVE, LEGACY, or all models
- **Region**: Filter by AWS region availability
- **Modality**: Filter by input/output modality (TEXT, IMAGE, EMBEDDING)
- **Reset**: Clear all filters with one click

## GitHub Deployment

### Setting Up the GitHub Repository

1. **Create a new public repository** named `amazonbedrockmodels.github.io`:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Bedrock models interactive table"
   git branch -M main
   git remote add origin https://github.com/amazonbedrockmodels/amazonbedrockmodels.github.io.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**:
   - Go to repository Settings → Pages
   - Select "Deploy from a branch"
   - Branch: `main`, Folder: `/ (root)`
   - Save

3. **Configure GitHub Secrets** for AWS credentials:
   - Go to Settings → Secrets and variables → Actions
   - Add `AWS_ACCESS_KEY_ID`
   - Add `AWS_SECRET_ACCESS_KEY`
   - These are used by the GitHub Actions workflow

   **Note**: Use a dedicated IAM user with minimal permissions (Bedrock read-only):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "bedrock:ListFoundationModels",
           "bedrock:ListInferenceProfiles"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "ec2:DescribeRegions"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

### GitHub Actions Workflow

The `.github/workflows/update-bedrock-data.yml` workflow:
- **Runs daily** at 00:00 UTC (configurable with cron syntax)
- **Fetches latest data** from AWS Bedrock APIs
- **Checks for changes** before committing
- **Auto-commits and pushes** only if data has changed
- **Can be manually triggered** via workflow_dispatch

## Frontend Architecture

### Key Components

- **Data Loading**: `loadData()` fetches `models.json` and `profiles.json`
- **Filtering**: `applyFilters()` applies all active filters and re-renders
- **Sorting**: `sortTable()` handles column sorting (ascending/descending)
- **Modal**: `openProfilesModal()` displays profiles for a selected model
- **Copy-to-Clipboard**: `copyToClipboard()` provides user feedback

### Filter Logic

Filters are combined with AND logic:
- Must match search term (if provided)
- Must match selected provider (if provided)
- Must match selected status (if provided)
- Must have selected region in its regions array (if provided)
- Must have selected modality in input OR output modalities (if provided)

## Future Enhancements

- [ ] Add Claude Code config generation for each model
- [ ] Add model pricing comparison
- [ ] Add latency/throughput comparisons
- [ ] Add export to CSV/JSON
- [ ] Add model changelog/version history
- [ ] Add custom pricing calculator
- [ ] Add favorited models list (localStorage)

## Troubleshooting

### Script fails with "No Bedrock-supported regions found"
- Check AWS credentials are configured correctly
- Ensure the IAM user has Bedrock permissions
- Verify network connectivity to AWS APIs

### Data files not updating
- Check GitHub Actions logs in the repository
- Verify AWS credentials are correctly set in GitHub Secrets
- Manually trigger the workflow via Actions tab

### Table not loading in browser
- Open browser DevTools (F12) and check Console for errors
- Verify `data/models.json` and `data/profiles.json` exist
- Check network requests to ensure files are being fetched

### Filters not working
- Clear browser cache
- Verify JavaScript is enabled
- Check browser console for JavaScript errors

## Contributing

This is an automated project, but feedback and issues are welcome!

## License

MIT

## Disclaimer

This is an unofficial, community-maintained project. AWS Bedrock information is provided as-is. Always refer to the [official AWS Bedrock documentation](https://docs.aws.amazon.com/bedrock/) for the most authoritative information.
