# webscraper

Scrape Webex help article release notes, filter by a configurable lookback window, and summarize the results with AI into a Markdown report.

Works with similarly structured pages such as:

- [Webex Contact Center administrators](https://help.webex.com/en-us/article/nv7abhz/What's-new-for-administrators-in-Webex-Contact-Center)
- [Control Hub](https://help.webex.com/en-us/article/u9dlxd/What's-new-in-Control-Hub)
- [Webex Suite](https://help.webex.com/en-us/article/8dmbcr/What's-New-in-Webex-Suite)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set the AI credentials in `.env` before running summarization (see `.env.example`).

## Usage

Scrape a Webex help article and write a 30-day report:

```bash
python -m webscraper --url "https://help.webex.com/en-us/article/u9dlxd/What's-new-in-Control-Hub"
```

Common options:

```bash
python -m webscraper \
  --url "https://help.webex.com/en-us/article/8dmbcr/What's-New-in-Webex-Suite" \
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

Reports are written to `output/{article-slug}-{date}-last{days}d.md` by default. The article title is read from the page metadata and used in the report heading and front matter.

Markdown output mirrors the source page structure:

- `##` tab name (What's new, Messaging, Announcements, etc.)
- `###` release date or month (`July 24, 2026` or `July 2026`)
- `####` feature title and summary bullets

Month-only headings (for example `July 2026` or `July (46.7)`) are treated as month-level releases. They are included when that month overlaps the lookback window, so current-month items are returned even without a specific day.

When AI summarization succeeds, the model is instructed to preserve this tab → date → feature structure. If AI is unavailable, the fallback report uses the same layout with scraped content.

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
| `AI_TIMEOUT_SECONDS` | No | HTTP timeout for AI requests in seconds (default: `120`) |

`AI_*` variables accept `CIRCUIT_*` aliases for compatibility with pamBot.

Authentication flow (matches Cisco Circuit / chat-ai.cisco.com):

1. Obtain OAuth access token via client credentials + HTTP Basic auth.
2. POST to `{AI_CHAT_BASE_URL}/{AI_MODEL_NAME}/chat/completions?api-version={AI_API_VERSION}` with:
   - Header `api-key: {access_token}` (OAuth token, not the app key)
   - JSON body including `"user": "{\"appkey\": \"...\"}"` using `AI_APP_KEY`

`AI_ENDPOINT` is still accepted as an alias for `AI_CHAT_BASE_URL`.

If the AI service times out or is otherwise unavailable, the CLI writes a fallback
markdown report listing the scraped release notes (with links preserved) instead of
exiting with a traceback.
