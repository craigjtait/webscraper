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
| `AI_APP_KEY` | Yes | Gateway API key (sent as `api-key` header by default) |
| `AI_ENDPOINT` | Yes | AI gateway base URL (e.g. `https://chat-ai.cisco.com`) |
| `AI_MODEL_NAME` | No | Deployment/model name (default: `gpt-5-nano`) |
| `AI_API_VERSION` | No | Azure-style API version (default: `2025-04-01-preview`) |
| `AI_TOKEN_URL` | No | OAuth token endpoint (default: Cisco `id.cisco.com`) |
| `AI_APP_KEY_HEADER` | No | Header name for `AI_APP_KEY` (default: `api-key`) |

Authentication flow:

1. Exchange `AI_CLIENT_ID` / `AI_CLIENT_SECRET` for a Bearer token via OAuth client credentials.
2. Call `{AI_ENDPOINT}/openai/deployments/{AI_MODEL_NAME}/chat/completions?api-version={AI_API_VERSION}` with the Bearer token and `api-key` header.

`AI_ENDPOINT` can be either the gateway base URL (`https://chat-ai.cisco.com`) or a path ending in `/openai/deployments`; the client avoids duplicating path segments.
