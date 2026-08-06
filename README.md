# confluence2md

Convert Confluence Data Center pages to Markdown with images, ready for GitHub Pages.

Give it any page URL and it produces a `.md` file plus an `images/` folder with all referenced attachments, links rewritten to relative paths. No PDF or Word export involved: it uses the Confluence REST API, so the conversion is deterministic and faithful.

## What it converts

Headings, bold/italics, tables (GFM), code blocks with language, info/note/warning panels (as blockquotes), task lists (checkboxes), attached and external images, links.

## Getting started

This repo is meant to be used as a template. Click **Use this template** to create your own copy (do not fork: template copies are cleaner and secrets are never inherited either way, so each copy configures its own).

### 1. Create a Personal Access Token

In Confluence: your avatar -> **Settings** -> **Personal Access Tokens** -> **Create token**. Copy it, it is only shown once.

### 2. Run locally (recommended first)

Create a virtual environment and install the dependencies:

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install requests beautifulsoup4 markdownify
```

```bash
# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 markdownify
```

```powershell
# Windows (PowerShell)
$env:CONFLUENCE_PAT = "your-token"
python scripts/confluence2md.py "https://confluence.company.com/pages/viewpage.action?pageId=12345" -o docs
```

```bash
# Linux/Mac
export CONFLUENCE_PAT="your-token"
python scripts/confluence2md.py "https://confluence.company.com/display/SPACE/My+Page" -o docs
```

Output: `docs/my-page.md` plus `docs/images/`.

![Important](https://img.shields.io/badge/IMPORTANT-!-red?style=flat-square)
If your Confluence uses an internal CA certificate and TLS verification fails, add `-k` (or better, point `REQUESTS_CA_BUNDLE` at the corporate certificate).

```bash
python scripts/confluence2md.py "https://confluence.company.com/display/SPACE/My+Page" -o docs -k
```

### 3. Automate with GitHub Actions (optional)

1. In your copy of the repo: **Settings -> Secrets and variables -> Actions** -> create secret `CONFLUENCE_PAT`.
2. (Optional) Create variable `CONFLUENCE_BASE_URL`, e.g. `https://confluence.company.com`.
3. You need a **self-hosted runner** inside the corporate network. GitHub-hosted runners cannot reach an internal Confluence. Runners are usually registered at the organization level, so create your copy inside the company organization; copies under personal GitHub accounts will not see the runner and can only use the script locally.
4. Go to **Actions -> Confluence to Markdown -> Run workflow**, paste the page URL, and the workflow converts the page, downloads the images and commits the result.

## Known limitations

Plugin macros (draw.io, Gliffy, Jira issues, etc.) have no Markdown equivalent. The script keeps their text content when available and prints a warning for the ones it skips. For draw.io diagrams, export them to PNG in Confluence so they travel as regular attachments.
