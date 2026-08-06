#!/usr/bin/env python3
"""
confluence2md.py - Convert a Confluence Data Center page to Markdown + images.

Usage:
    export CONFLUENCE_PAT="your-personal-access-token"
    python confluence2md.py "https://confluence.company.com/pages/viewpage.action?pageId=12345" -o docs

Accepted URL formats (or a numeric pageId directly):
    .../pages/viewpage.action?pageId=12345
    .../pages/12345/Page+Title
    .../display/SPACE/Page+Title

Output:
    <outdir>/<page-title-slug>.md
    <outdir>/images/<referenced attachments>

Dependencies: pip install requests beautifulsoup4 markdownify
"""

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md

IMG_DIR_NAME = "images"


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def slugify(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text) or "page"


def guess_base_url(url: str) -> str:
    """Infer the Confluence base URL (including context path such as /confluence)."""
    for marker in ("/pages/", "/display/", "/spaces/"):
        if marker in url:
            return url.split(marker)[0]
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def build_session(pat: str, insecure: bool) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {pat}"
    s.headers["Accept"] = "application/json"
    if insecure:
        s.verify = False
        import urllib3
        urllib3.disable_warnings()
    return s


def resolve_page_id(url_or_id: str, base: str, session: requests.Session) -> str:
    if url_or_id.isdigit():
        return url_or_id
    # ?pageId=12345
    qs = parse_qs(urlparse(url_or_id).query)
    if "pageId" in qs:
        return qs["pageId"][0]
    # /pages/12345/Title
    m = re.search(r"/pages/(\d+)", url_or_id)
    if m:
        return m.group(1)
    # /display/SPACE/Title -> look up through the API
    m = re.search(r"/display/([^/]+)/([^/?#]+)", url_or_id)
    if m:
        space, title = m.group(1), unquote(m.group(2).replace("+", " "))
        r = session.get(f"{base}/rest/api/content",
                        params={"spaceKey": space, "title": title, "limit": 1})
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            die(f"Page '{title}' not found in space {space}")
        return results[0]["id"]
    die(f"Could not extract a pageId from: {url_or_id}")


def fetch_page(base: str, page_id: str, session: requests.Session) -> dict:
    r = session.get(f"{base}/rest/api/content/{page_id}",
                    params={"expand": "body.storage,space"})
    if r.status_code == 401:
        die("401 Unauthorized: check your CONFLUENCE_PAT")
    if r.status_code == 404:
        die(f"404: page {page_id} does not exist or you lack permission")
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- conversion

PANEL_MACROS = {"info": "Info", "note": "Note", "warning": "Warning",
                "tip": "Tip", "panel": ""}


def storage_to_markdown(storage_html: str, title: str):
    """Convert Confluence storage format (XHTML) to GFM Markdown.

    Returns (markdown, set of referenced attachment filenames).
    """
    soup = BeautifulSoup(storage_html, "html.parser")
    referenced = set()
    code_blocks = {}

    # --- Structured macros ---
    for i, macro in enumerate(list(soup.find_all("ac:structured-macro"))):
        name = (macro.get("ac:name") or "").lower()
        if name == "code":
            lang = ""
            for p in macro.find_all("ac:parameter"):
                if p.get("ac:name") == "language":
                    lang = p.get_text(strip=True)
            body = macro.find("ac:plain-text-body")
            code = body.get_text() if body else ""
            key = f"XCODEBLOCKX{i}X"
            code_blocks[key] = f"```{lang}\n{code.strip()}\n```"
            ph = soup.new_tag("p")
            ph.string = key
            macro.replace_with(ph)
        elif name in PANEL_MACROS:
            body = macro.find("ac:rich-text-body")
            bq = soup.new_tag("blockquote")
            label = PANEL_MACROS[name]
            if label:
                p = soup.new_tag("p")
                b = soup.new_tag("strong")
                b.string = label
                p.append(b)
                bq.append(p)
            if body:
                for child in list(body.children):
                    bq.append(child.extract())
            macro.replace_with(bq)
        elif name == "toc":
            macro.decompose()  # GitHub renders its own TOC
        else:
            # Unknown macro: keep its rich body if present
            body = macro.find("ac:rich-text-body")
            if body:
                macro.replace_with(body)
            else:
                print(f"  WARNING: macro '{name}' has no Markdown equivalent, skipped")
                macro.decompose()

    # --- Images ---
    for ac_img in list(soup.find_all("ac:image")):
        att = ac_img.find("ri:attachment")
        ext = ac_img.find("ri:url")
        new = None
        if att and att.get("ri:filename"):
            fn = att["ri:filename"]
            referenced.add(fn)
            new = soup.new_tag("img", src=f"{IMG_DIR_NAME}/{quote(fn)}",
                               alt=ac_img.get("ac:alt", fn))
        elif ext and ext.get("ri:value"):
            new = soup.new_tag("img", src=ext["ri:value"], alt="")
        if new is not None:
            ac_img.replace_with(new)
        else:
            ac_img.decompose()

    # --- Internal Confluence links ---
    for link in list(soup.find_all("ac:link")):
        page_ref = link.find("ri:page")
        body = link.find("ac:plain-text-link-body") or link.find("ac:link-body")
        text = (body.get_text() if body else
                page_ref.get("ri:content-title", "") if page_ref else "")
        link.replace_with(soup.new_string(text or ""))

    # --- Task lists ---
    for tl in list(soup.find_all("ac:task-list")):
        ul = soup.new_tag("ul")
        for task in tl.find_all("ac:task"):
            status = task.find("ac:task-status")
            body = task.find("ac:task-body")
            li = soup.new_tag("li")
            mark = "[x] " if status and status.get_text(strip=True) == "complete" else "[ ] "
            li.string = mark + (body.get_text(strip=True) if body else "")
            ul.append(li)
        tl.replace_with(ul)

    for emo in list(soup.find_all("ac:emoticon")):
        emo.decompose()

    md = html_to_md(str(soup), heading_style="ATX", bullets="-")

    for key, block in code_blocks.items():
        md = md.replace(key, block)

    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return f"# {title}\n\n{md}\n", referenced


# ---------------------------------------------------------------- attachments

def download_images(session: requests.Session, base: str, page_id: str,
                    referenced: set, outdir: Path):
    if not referenced:
        return
    img_dir = outdir / IMG_DIR_NAME
    img_dir.mkdir(parents=True, exist_ok=True)

    # Map filename -> download link
    links, start = {}, 0
    while True:
        r = session.get(f"{base}/rest/api/content/{page_id}/child/attachment",
                        params={"limit": 100, "start": start})
        r.raise_for_status()
        data = r.json()
        for a in data.get("results", []):
            links[a["title"]] = a["_links"]["download"]
        if len(data.get("results", [])) < 100:
            break
        start += 100

    for fn in sorted(referenced):
        link = links.get(fn) or f"/download/attachments/{page_id}/{quote(fn)}"
        r = session.get(base + link)
        if r.status_code != 200:
            print(f"  WARNING: could not download {fn} (HTTP {r.status_code})")
            continue
        (img_dir / fn).write_bytes(r.content)
        print(f"  OK {IMG_DIR_NAME}/{fn}")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Confluence DC to Markdown")
    ap.add_argument("page", help="Page URL or numeric pageId")
    ap.add_argument("-o", "--outdir", default="docs", help="Output folder (default: docs)")
    ap.add_argument("-b", "--base-url", default=os.environ.get("CONFLUENCE_BASE_URL"),
                    help="Confluence base URL (inferred from the page URL if omitted)")
    ap.add_argument("-k", "--insecure", action="store_true",
                    help="Skip TLS certificate verification (internal CAs)")
    args = ap.parse_args()

    pat = os.environ.get("CONFLUENCE_PAT")
    if not pat:
        die("Set the CONFLUENCE_PAT environment variable (Personal Access Token)")

    base = (args.base_url or guess_base_url(args.page)).rstrip("/")
    session = build_session(pat, args.insecure)

    page_id = resolve_page_id(args.page, base, session)
    print(f"Page {page_id} at {base}")

    page = fetch_page(base, page_id, session)
    title = page["title"]
    storage = page["body"]["storage"]["value"]

    markdown, referenced = storage_to_markdown(storage, title)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    md_path = outdir / f"{slugify(title)}.md"
    md_path.write_text(markdown, encoding="utf-8")
    print(f"  OK {md_path}")

    download_images(session, base, page_id, referenced, outdir)
    print("Done.")


if __name__ == "__main__":
    main()
