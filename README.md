# webscraper

Scrape Webex Contact Center administrator release notes, filter by a configurable lookback window, and summarize the results with AI into a Markdown report.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` before running summarization.

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

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key for summarization |
| `OPENAI_MODEL` | Model name (default: `gpt-4o-mini`) |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint |
