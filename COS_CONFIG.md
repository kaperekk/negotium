# Cloud Object Storage (COS) Configuration

This guide explains how to configure Negotium to use S3-compatible cloud object storage (like Cloudflare R2, AWS S3, MinIO, etc.) for persistent data storage on Streamlit Cloud.

## Why COS?

Streamlit Cloud restarts pods periodically, which loses all local filesystem data. Using COS ensures your data persists across restarts.

## Supported Providers

Any S3-compatible storage works:
- **Cloudflare R2** (Recommended: 10GB free, no egress fees)
- **AWS S3** (5GB free for 12 months)
- **Backblaze B2** (10GB free)
- **Google Cloud Storage** (5GB free)
- **MinIO** (self-hosted)
- **DigitalOcean Spaces**

## Configuration

Add the following to your Streamlit Cloud secrets (Settings → Secrets):

```toml
[cos]
bucket = "your-bucket-name"
endpoint = "https://your-account-id.r2.cloudflarestorage.com"  # For R2
region = "auto"  # For R2, use "auto"
access_key = "your-access-key-id"
secret_key = "your-secret-access-key"
prefix = "negotiun/"  # Optional: prefix for all keys (trailing slash added automatically)
```

### Provider-Specific Examples

#### Cloudflare R2
```toml
[cos]
bucket = "negotiun-data"
endpoint = "https://<account-id>.r2.cloudflarestorage.com"
region = "auto"
access_key = "<your-access-key>"
secret_key = "<your-secret-key>"
prefix = "negotiun/"
```

#### AWS S3
```toml
[cos]
bucket = "negotiun-data"
region = "us-east-1"
access_key = "<your-access-key>"
secret_key = "<your-secret-key>"
prefix = "negotiun/"
```

#### MinIO (local development)
```toml
[cos]
bucket = "negotiun"
endpoint = "http://localhost:9000"
region = "us-east-1"
access_key = "minioadmin"
secret_key = "minioadmin"
prefix = "negotiun/"
```

## How It Works

The storage backend abstraction (`src/storage/backends.py`) provides two implementations:

1. **LocalBackend** - Default, uses local filesystem (`data/`)
2. **S3Backend** - Uses boto3 for S3-compatible storage

The backend is automatically selected based on the presence of COS secrets. If `bucket`, `access_key`, and `secret_key` are configured, `S3Backend` is used; otherwise `LocalBackend` is used.

## Data Structure in COS

All data is stored under the configured prefix:

```
<prefix>/
├── config.json                 # Global config
├── users.json                  # User registry (UUID → username)
├── projects.json               # Project registry
├── ticker_names.json           # Ticker name cache
├── ticker_meta.json            # Ticker metadata cache
├── ath.json                    # All-time highs cache
├── earnings.json               # Earnings cache
├── prices/                     # Price cache (yearly files)
│   └── <TICKER>/
│       └── <YEAR>.json
├── prices_adj/                 # Adjusted price cache
├── dividends/                  # Dividend cache
│   └── <TICKER>.json
└── users/
    └── <username>/
        ├── config.json         # User config
        └── <project>/
            ├── transactions.jsonl
            ├── portfolio.jsonl
            ├── balance.json
            ├── benchmarks_<CCY>.json
            └── imports/
                ├── xtb/
                ├── bossa/
                └── custom/
```

## Local Development

For local development without COS, no configuration is needed - it uses the local filesystem automatically.

To test with COS locally, you can:
1. Set environment variables instead of Streamlit secrets:
   ```bash
   export COS_BUCKET=your-bucket
   export COS_ENDPOINT=https://your-endpoint
   export COS_ACCESS_KEY=your-key
   export COS_SECRET_KEY=your-secret
   export COS_PREFIX=negotiun/
   ```
2. Or create `.streamlit/secrets.toml` in your project root (gitignored)

## Migration from Local to COS

If you have existing local data and want to migrate to COS:

1. Configure COS secrets
2. Deploy to Streamlit Cloud (will start fresh)
3. Or manually upload your `data/` directory to the bucket with the same structure

## Troubleshooting

### "boto3 not installed"
Run: `pip install boto3`

### "Credentials not found"
Ensure all three are set: `bucket`, `access_key`, `secret_key`

### "Access Denied"
Check your credentials and bucket permissions. For R2, ensure the API token has Object Read/Write permissions.

### "Connection timeout"
Check the endpoint URL. For R2, it should be `https://<account-id>.r2.cloudflarestorage.com`

### Data not persisting
- Verify the backend is using S3Backend: check logs for "Using S3Backend"
- Ensure the prefix is correct (no leading slash, trailing slash added automatically)
- Check bucket permissions

## Security Notes

- Never commit secrets to git
- Use Streamlit Cloud's encrypted secrets management
- Rotate credentials periodically
- Use least-privilege API tokens (e.g., R2 scoped tokens)