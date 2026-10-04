# Negotium Architecture & Run Guide

## Two Entry Points

| File | Description | Backend |
|------|-------------|---------|
| `src/app_local.py` | Direct access, no login, local-only storage | LocalBackend only |
| `src/app.py` | Login with UUID key, loads `.env` for COS | SyncBackend (if .env present) |

---

## Using the Launcher Script (`scripts/start.sh`)

The `scripts/start.sh` script is the recommended way to run Negotium. It handles:

- **Python detection** — Finds Python 3.10+ (prefers 3.14, falls back to 3.13/3.12/3.11)
- **Virtualenv management** — Creates `.venv/` on first run, reuses it thereafter
- **Dependency installation** — Installs/updates packages from `requirements.txt`
- **Optional test runner** — Runs pytest before starting the app
- **Data reset** — `--reset` wipes all data and starts fresh

### Usage

```bash
./start.sh                 # Start UI (skip tests, uses local-only app_local.py)
./start.sh --run-tests     # Run tests, then start UI
./start.sh --tests-only    # Run tests only, don't start UI
./start.sh --port 8502     # Custom port (default 8501)
./start.sh --reset         # Wipe all data and start fresh
./start.sh -h              # Show help
```

### What it does

1. Detects Python ≥ 3.10
2. Creates/uses `.venv/` virtualenv in project root
3. Installs/updates dependencies from `requirements.txt`
4. Runs tests if `--run-tests` or `--tests-only` flag provided
5. Launches `src/app_local.py` via Streamlit on specified port

> **Note**: The launcher always starts `app_local.py` (local-only mode). For multi-user with COS sync, run `streamlit run src/app.py` manually with `.env` configured.

---

## Running app.py (with Login + COS Sync)

### 1. Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
# Or manually:
pip install streamlit pandas openpyxl orjson python-dotenv boto3 yfinance
```

### 2. Configure `.env` (for COS / Cloudflare R2)

Create `.env` in project root (already exists):

```env
COS_BUCKET=negotium-data
COS_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
COS_ACCESS_KEY=<your-access-key>
COS_SECRET_KEY=<your-secret-key>
COS_PREFIX=negotium/
COS_REGION=auto
```

**Required**: `COS_BUCKET`, `COS_ACCESS_KEY`, `COS_SECRET_KEY`  
**Optional**: `COS_ENDPOINT` (defaults to AWS S3), `COS_PREFIX`, `COS_REGION`

### 3. Create a User (First Time)

```bash
python scripts/create_user.py "Your Name"
```

Output:
```
User created: a1b2c3d4-e5f6-7890-abcd-ef1234567890
User key: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Save this UUID key** — it's your login credential.

### 4. Start the App

```bash
streamlit run src/app.py
```

Opens at `http://localhost:8501`

### 5. Login

- Enter your **User Key (UUID)** on the login page
- Click **Login**
- You'll see your projects and data

---

## Running app_local.py (Direct Access, No COS)

```bash
streamlit run src/app_local.py
```

- No login required
- Uses `local_user` account
- **No COS sync** — data stays local only
- No `.env` needed

---

## Storage Backends

| App | Env Var | Backend | COS Sync Button |
|-----|---------|---------|-----------------|
| `app.py` | none / `.env` loaded | `SyncBackend` (local + COS) | ✅ Visible |
| `app_local.py` | `NEGOTIUM_LOCAL_ONLY=true` | `LocalBackend` only | ❌ Hidden |

---

## Data Structure

```
data/
├── users/
│   ├── local_user/           # app_local.py data
│   └── <uuid>/               # per-user data (app.py)
│       ├── projects.json
│       ├── <project>/
│       │   ├── transactions.jsonl
│       │   ├── portfolio.jsonl
│       │   ├── balance.json
│       │   └── imports/
│       │       ├── xtb/
│       │       ├── bossa/
│       │       └── custom/
│       └── config.json
├── users.json                # user registry (key -> {user_name, created})
└── prices/                   # cached price data (shared)
```

---

## Key Differences

| Feature | app.py | app_local.py |
|---------|--------|--------------|
| Authentication | UUID key login | None (auto local_user) |
| Multi-user | Yes | No |
| COS/R2 Sync | Yes (if .env configured) | No |
| Sync button in UI | ✅ | ❌ |
| .env loading | Yes (via python-dotenv) | No |

---

## Troubleshooting

**"Invalid user key"**
- Verify the UUID from `create_user.py` output
- Check `data/users.json` exists and has your key

**"boto3 not installed"**
```bash
pip install boto3
```

**"COS not configured"**
- Ensure `.env` has all required vars
- Restart app after changing `.env`

**Port already in use**
```bash
streamlit run src/app.py --server.port 8502
```