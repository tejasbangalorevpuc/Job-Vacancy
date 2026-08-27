#!/usr/bin/env python3
"""
Bengaluru Senior Admin/Procurement Vacancy Watcher
----------------------------------------------------
Checks a configured list of organization career pages, extracts candidate
posting lines, diffs against previously-seen postings (state/seen.json),
scores new ones against your profile, and:
  - appends matches to docs/results.json (for the dashboard)
  - sends a Telegram notification for NEW high/medium relevance matches

Run daily via GitHub Actions (see .github/workflows/daily-check.yml) or cron.

Env vars (optional, for notifications):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import re
import json
import hashlib
import datetime
import urllib.request
import urllib.error

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_DIR = os.path.join(BASE_DIR, "state")
STATE_PATH = os.path.join(STATE_DIR, "seen.json")
RESULTS_PATH = os.path.join(BASE_DIR, "docs", "results.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def fetch_page(url: str) -> str:
    """Fetch page text; falls back to urllib if requests isn't installed."""
    try:
        if requests:
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            html = resp.text
        else:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                html = r.read().decode("utf-8", errors="ignore")
        return html
    except Exception as e:
        print(f"  [warn] failed to fetch {url}: {e}")
        return ""


def extract_text_lines(html: str) -> list:
    """Pull visible text lines and link text out of the HTML."""
    if not html:
        return []
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        lines = []
        # Links are usually where posting titles live (e.g. "Deputy Registrar - PDF")
        for a in soup.find_all("a"):
            t = a.get_text(" ", strip=True)
            if t and len(t) > 8:
                lines.append(t)
        # Also grab list items / paragraphs / table rows
        for tag in soup.find_all(["li", "p", "td", "h1", "h2", "h3", "h4"]):
            t = tag.get_text(" ", strip=True)
            if t and len(t) > 8:
                lines.append(t)
        # de-dup while preserving order
        seen = set()
        out = []
        for l in lines:
            if l not in seen:
                seen.add(l)
                out.append(l)
        return out
    else:
        # crude fallback without bs4
        text = re.sub(r"<[^>]+>", "\n", html)
        return [l.strip() for l in text.splitlines() if len(l.strip()) > 8]


# --------------------------------------------------------------------------
# Matching / scoring
# --------------------------------------------------------------------------

def line_hash(org: str, line: str) -> str:
    return hashlib.sha256(f"{org}::{line}".encode("utf-8")).hexdigest()


def keyword_hits(line: str, keywords: list) -> list:
    lline = line.lower()
    return [k for k in keywords if k.lower() in lline]


def score_match(line: str, profile: dict, keyword_hit_count: int) -> str:
    lline = line.lower()
    score = 0
    if any(loc.lower() in lline for loc in profile.get("location_preference", [])):
        score += 1
    if any(emp.lower() in lline for emp in profile.get("employer_types", [])):
        score += 1
    if any(et.lower() in lline for et in profile.get("employment_type_preference", [])):
        score += 1
    if any(area.lower() in lline for area in profile.get("experience_areas", [])):
        score += 1
    score += keyword_hit_count

    if score >= 4:
        return "High"
    elif score >= 2:
        return "Medium"
    else:
        return "Low"


def pay_protection_flag(line: str, profile: dict) -> str:
    lline = line.lower()
    hits = [k for k in profile.get("pay_protection_flag_keywords", []) if k.lower() in lline]
    if hits:
        return "Likely — verify appointment terms (" + ", ".join(hits) + ")"
    return "Unclear — check advertisement"


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Notification
# --------------------------------------------------------------------------

def send_telegram(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("  [info] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping Telegram send.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        if requests:
            r = requests.post(url, data=data, timeout=15)
            if r.status_code != 200:
                print(f"  [warn] Telegram send failed: {r.text}")
        else:
            payload = urllib.parse.urlencode(data).encode()
            req = urllib.request.Request(url, data=payload)
            urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"  [warn] Telegram send error: {e}")


def format_notification(org: str, line: str, relevance: str, keywords: list, protection: str) -> str:
    return (
        f"*NEW VACANCY — {org}*\n"
        f"Post/Line: {line[:300]}\n"
        f"Matched terms: {', '.join(keywords) if keywords else '(profile match only)'}\n"
        f"Your profile match: *{relevance}*\n"
        f"Pay-protection potential: {protection}\n"
        f"Source: {org}\n"
        f"— verify full details on the official page before acting."
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    config = load_json(CONFIG_PATH, {})
    orgs = config.get("organizations", [])
    keywords = config.get("keywords_any", [])
    profile = config.get("profile", {})

    seen = load_json(STATE_PATH, {})  # hash -> {org, line, first_seen}
    results = load_json(RESULTS_PATH, {"last_run": None, "new_this_run": [], "all_matches": []})

    new_matches = []
    run_time = datetime.datetime.utcnow().isoformat() + "Z"

    for org in orgs:
        name = org["name"]
        url = org["url"]
        print(f"Checking {name} -> {url}")
        html = fetch_page(url)
        lines = extract_text_lines(html)
        if len(lines) < 5:
            print(f"  [warn] very little content extracted — URL may be stale. Check manually: {url}")
            continue

        for line in lines:
            hits = keyword_hits(line, keywords)
            if not hits:
                continue  # only care about lines matching at least one target keyword

            h = line_hash(name, line)
            if h in seen:
                continue  # already notified before

            relevance = score_match(line, profile, len(hits))
            protection = pay_protection_flag(line, profile)

            record = {
                "hash": h,
                "org": name,
                "source_url": url,
                "line": line,
                "matched_keywords": hits,
                "relevance": relevance,
                "pay_protection": protection,
                "first_seen": run_time,
            }
            seen[h] = {"org": name, "line": line, "first_seen": run_time}
            new_matches.append(record)

    # Save state + results regardless of whether there were matches
    save_json(STATE_PATH, seen)
    results["last_run"] = run_time
    results["new_this_run"] = new_matches
    results["all_matches"] = new_matches + results.get("all_matches", [])
    results["all_matches"] = results["all_matches"][:500]  # cap history
    save_json(RESULTS_PATH, results)

    if new_matches:
        print(f"\n{len(new_matches)} new potential match(es) found:\n")
        for m in new_matches:
            msg = format_notification(m["org"], m["line"], m["relevance"], m["matched_keywords"], m["pay_protection"])
            print(msg + "\n")
            if m["relevance"] in ("High", "Medium"):
                send_telegram(msg)
    else:
        print("\nNo new matches this run.")


if __name__ == "__main__":
    main()
