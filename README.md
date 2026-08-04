# webscraper

A Python CLI that scrapes Webex help article release notes, filters them by a configurable lookback window, and produces a structured Markdown report with optional AI summarization.

## Project scope

### What it does

1. **Fetch** a Webex help article from `help.webex.com` (including embedded Next.js `UIData` HTML).
2. **Parse** release notes from all navigation tabs on the page, preserving tab names, release dates/months, feature titles, body text, and links.
3. **Filter** features to those within a `--days` lookback window relative to an `--as-of` reference date.
4. **Summarize** filtered content with Cisco Circuit AI (optional; skipped with `--dry-run`).
5. **Write** a Markdown report with YAML front matter to the `output/` directory.

### Supported pages

The parser is designed for similarly structured Webex "What's new" articles. Tested examples include:

| Page | URL |
|------|-----|
| Webex Contact Center administrators | https://help.webex.com/en-us/article/nv7abhz/What's-new-for-administrators-in-Webex-Contact-Center |
| Control Hub | https://help.webex.com/en-us/article/u9dlxd/What's-new-in-Control-Hub |
| Webex Suite | https://help.webex.com/en-us/article/8dmbcr/What's-New-in-Webex-Suite |

Pages may organize content differently, but generally share:

- Bootstrap-style **tab navigation** (What's new, Messaging, Calling, Announcements, Coming soon, etc.).
- **Date or month headings** (`July 24, 2026`, `July 2026`, `July (46.7)`).
- **Feature entries** as headings (h2–h4) with paragraphs, lists, and links.

The article title is read automatically from page metadata and used in the report heading and default output filename.

### What it does not do

- Scrape pages that require authentication beyond public help article access.
- Monitor pages on a schedule (run manually or via cron/external automation).
- Modify or publish back to Webex.

---

## Requirements

### Python environment

- **Python 3.9.6 or newer** (see `requires-python` in `pyproject.toml`).
- A virtual environment is recommended.

### Runtime dependencies

Installed automatically with `pip install -e ".[dev]"`:

| Package | Purpose |
|---------|---------|
| `httpx` | HTTP client for fetching pages and AI API calls |
| `beautifulsoup4` + `lxml` | HTML parsing |
| `python-dateutil` | Flexible date parsing |
| `python-dotenv` | Load `.env` configuration |
| `typer` | CLI framework |

### Network access

- Outbound HTTPS to `help.webex.com` (and optionally CloudFront content mirrors).
- Outbound HTTPS to Cisco OAuth (`id.cisco.com`) and the AI chat endpoint (`chat-ai.cisco.com` by default) when summarization is enabled.

### AI integration (for summarization)

Summarization requires Cisco Circuit / chat-ai credentials. These are **not** needed when using `--dry-run`.

| Credential | Purpose |
|------------|---------|
| OAuth client ID + secret | Obtain a short-lived access token via client credentials |
| Circuit app key | Identifies your application in the chat completions request body |

Credentials are loaded from a `.env` file or the process environment. See [AI configuration](#ai-configuration) below.

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/craigjtait/webscraper.git
cd webscraper

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install the package

```bash
pip install -e ".[dev]"
```

This installs the `webscraper` console script and development tools (`pytest`, `ruff`).

### 3. Configure AI credentials

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
AI_CLIENT_ID=your-client-id
AI_CLIENT_SECRET=your-client-secret
AI_APP_KEY=your-circuit-app-key
```

Optional settings and aliases are documented in [AI configuration](#ai-configuration).

### 4. Verify installation

Parse only (no AI credentials required):

```bash
python -m webscraper --dry-run --days 7
```

---

## Usage

Run the CLI with either:

```bash
python -m webscraper [OPTIONS]
```

or, after installation:

```bash
webscraper [OPTIONS]
```

### Quick start

Default URL (Contact Center administrators), 30-day lookback, AI summarization:

```bash
python -m webscraper
```

Scrape a specific article:

```bash
python -m webscraper --url "https://help.webex.com/en-us/article/u9dlxd/What's-new-in-Control-Hub"
```

Parse and filter only (no AI call):

```bash
python -m webscraper --url "https://help.webex.com/en-us/article/8dmbcr/What's-New-in-Webex-Suite" --dry-run --days 7
```

### Command-line parameters

| Option | Default | Description |
|--------|---------|-------------|
| `--url` | Contact Center admin URL (see `cli.py`) | Full URL of the Webex help article to scrape. Fragment anchors (`#...`) in the URL are ignored; all tabs on the page are parsed. |
| `--days` | `30` | Lookback window in days. Must be ≥ 1. Features outside this window are excluded from the report. |
| `--as-of` | Today (`YYYY-MM-DD`) | Reference date for the lookback calculation. Useful for reproducible reports or backdating. |
| `--output` | `output/{article-slug}-{date}-last{days}d.md` | Path to the output Markdown file. Parent directories are created automatically. |
| `--cache-dir` | *(none)* | If set, caches fetched page HTML to `{cache-dir}/page.html` for faster offline re-runs. |
| `--dry-run` | `false` | Parse and filter only. Prints matching features grouped by tab to stdout and exits without calling AI or writing a report. |

#### Examples

Seven-day report as of a specific date:

```bash
python -m webscraper \
  --days 7 \
  --as-of 2026-07-30 \
  --output output/control-hub-weekly.md \
  --url "https://help.webex.com/en-us/article/u9dlxd/What's-new-in-Control-Hub"
```

Re-use cached HTML while iterating on filters:

```bash
python -m webscraper --cache-dir .cache --dry-run --days 30
```

---

## How it works

```
help.webex.com article URL
        │
        ▼
   fetch_article()          ← page title + UIData HTML
        │
        ▼
   parse_release_features() ← all tabs; h2–h4 headings; links
        │
        ▼
   filter_by_lookback()     ← --days / --as-of
        │
        ▼
   summarize_features()     ← Cisco Circuit AI (or fallback)
        │
        ▼
   output/*.md              ← YAML front matter + Markdown body
```

### Parsing and filtering

- **Tabs:** Every top-level tab pane linked from the page navigation is parsed (e.g. What's new, Messaging, Announcements).
- **Headings:** Period headings (dates/months) are distinguished from feature titles. Features may appear as h2, h3, or h4 depending on the page.
- **Date formats recognized:**
  - Full date: `July 24, 2026`
  - Month and year: `July 2026`, `March, 2026`
  - Month and release version: `July (46.7)` — year inferred from `--as-of`
- **Month-only filtering:** Month-level entries are included when their calendar month overlaps the lookback window, so current-month releases appear even without a specific day.
- **Links:** Anchor tags in feature body text are preserved as Markdown links in the output.

### AI summarization and fallback

When AI summarization succeeds, the model receives structured input grouped by tab and date, and is instructed to produce Markdown with the same hierarchy.

If the AI service **times out** or returns an error, the CLI:

1. Prints a warning to stderr (no traceback).
2. Writes a **fallback report** using scraped content in the same tab → date → feature layout.
3. Exits successfully with a usable report file.

Fallback reports include `ai_fallback: true` in the YAML front matter.

---

## Output

### Default filename

```
output/{article-slug}-{as-of-date}-last{days}d.md
```

Example: `output/whats-new-in-control-hub-2026-07-30-last30d.md`

### Report structure

**YAML front matter** (example):

```yaml
---
title: What's new in Control Hub
source: https://help.webex.com/en-us/article/u9dlxd/...
lookback_days: 30
as_of: 2026-07-30
date_range: 2026-07-01 to 2026-07-24
generated_at: 2026-07-30T17:00:00+00:00
feature_count: 37
tabs: What's new, Coming soon
---
```

**Markdown body** mirrors the source page:

```markdown
# What's new in Control Hub — Last 30 Days (as of July 30, 2026)

## What's new

### July 2026

#### Improved localization for Control Hub analytics

- Summary bullet points…

## Messaging

### July 2026

#### UI enhancements for messaging area—Android
```

---

## AI configuration

### Required variables

| Variable | Description |
|----------|-------------|
| `AI_CLIENT_ID` | OAuth client ID for token acquisition |
| `AI_CLIENT_SECRET` | OAuth client secret |
| `AI_APP_KEY` | Circuit app key (sent in JSON `user.appkey`) |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_CHAT_BASE_URL` | `https://chat-ai.cisco.com/openai/deployments` | Deployments base URL for chat completions |
| `AI_MODEL_NAME` | `gpt-5-nano` | Model/deployment name |
| `AI_API_VERSION` | `2025-04-01-preview` | Azure-style API version query parameter |
| `AI_SCOPE` | *(empty)* | OAuth scope, if required by your API console registration |
| `AI_TOKEN_URL` | `https://id.cisco.com/oauth2/default/v1/token` | OAuth token endpoint |
| `AI_TIMEOUT_SECONDS` | `120` | HTTP timeout for AI requests (seconds) |

### Aliases

For compatibility with pamBot / Circuit tooling, `CIRCUIT_*` environment variables are accepted as fallbacks for the corresponding `AI_*` variables (for example `CIRCUIT_CLIENT_ID` → `AI_CLIENT_ID`).

`AI_ENDPOINT` is accepted as an alias for `AI_CHAT_BASE_URL`.

### Authentication flow

The integration follows the Cisco Circuit / chat-ai.cisco.com pattern:

1. **Obtain an OAuth access token** using client credentials with HTTP Basic auth (`client_id:client_secret` base64-encoded).
2. **POST** to `{AI_CHAT_BASE_URL}/{AI_MODEL_NAME}/chat/completions?api-version={AI_API_VERSION}` with:
   - Header `api-key: {access_token}` — the OAuth token, **not** the app key
   - JSON body including `"user": "{\"appkey\": \"...\"}"` using `AI_APP_KEY`

See `.env.example` for a complete template.

---

## Tests

Run the unit test suite (uses local HTML fixtures; no network required):

```bash
pytest
```

Run linting:

```bash
ruff check src tests
```

Integration tests that hit the live Webex site are marked separately:

```bash
pytest -m integration
```

---

## Project layout

```
webscraper/
├── src/webscraper/
│   ├── cli.py           # Typer CLI entry point
│   ├── fetcher.py       # Page fetch and UIData extraction
│   ├── parser.py        # Tab/heading parsing
│   ├── filter.py        # Lookback date filtering
│   ├── ai_client.py     # Cisco Circuit OAuth + chat completions
│   ├── summarizer.py    # AI prompt, fallback, and report assembly
│   └── models.py        # ReleaseFeature dataclass
├── tests/               # Unit tests and HTML fixtures
├── output/              # Generated reports (gitignored)
├── .env.example         # Environment variable template
└── pyproject.toml       # Package metadata and dependencies
```
