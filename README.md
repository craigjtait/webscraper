# webscraper

Scrape Webex Contact Center administrator release notes, filter by a configurable lookback window, and summarize the results with AI into a Markdown report.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set the AI credentials in `.env` before running summarization (see `.env.example`).

## Usage

Scrape the default Webex admin "What's new" page and write a 30-day report:

```bash
python -m webscraper
```

Common options:

```bash
python -m webscraper \
  --days 7 \
  --as-of 2026-07-30 \
  --output output/report.md \
  --dry-run
```

- `--days`: lookback window in days (default: 30)
- `--as-of`: reference date in `YYYY-MM-DD` format (default: today)
- `--url`: article URL to scrape
- `--output`: output markdown path
- `--cache-dir`: cache fetched HTML for offline re-runs
- `--dry-run`: parse and filter only; skip AI summarization

## Output

Reports are written to `output/webex-cc-admin-updates-{date}-last{days}d.md` by default and include YAML front matter plus AI-generated Markdown summaries grouped by release date.

## Tests

```bash
pytest
```

Integration tests that hit the live Webex site are marked separately:

```bash
pytest -m integration
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_CLIENT_ID` | Yes | OAuth client ID for token acquisition |
| `AI_CLIENT_SECRET` | Yes | OAuth client secret |
| `AI_APP_KEY` | Yes | Circuit app key (sent in JSON `user.appkey`) |
| `AI_CHAT_BASE_URL` | No | Deployments base URL (default: `https://chat-ai.cisco.com/openai/deployments`) |
| `AI_MODEL_NAME` | No | Deployment/model name (default: `gpt-5-nano`) |
| `AI_API_VERSION` | No | API version (default: `2025-04-01-preview`) |
| `AI_SCOPE` | No | OAuth scope (`CIRCUIT_OAUTH_SCOPE` alias supported) |
| `AI_TOKEN_URL` | No | OAuth token endpoint (default: Cisco `id.cisco.com`) |

`AI_*` variables accept `CIRCUIT_*` aliases for compatibility with pamBot.

Authentication flow (matches Cisco Circuit / chat-ai.cisco.com):

1. Obtain OAuth access token via client credentials + HTTP Basic auth.
2. POST to `{AI_CHAT_BASE_URL}/{AI_MODEL_NAME}/chat/completions?api-version={AI_API_VERSION}` with:
   - Header `api-key: {access_token}` (OAuth token, not the app key)
   - JSON body including `"user": "{\"appkey\": \"...\"}"` using `AI_APP_KEY`

`AI_ENDPOINT` is still accepted as an alias for `AI_CHAT_BASE_URL`.
