# Bengaluru Senior Admin / Procurement Vacancy Watcher

Checks IISc, NCBS-TIFR, ICTS-TIFR, RRI, NIMHANS, CPRI, CSIR-NAL, NLSIU, IIIT-B,
BEL, BEML, HAL and ISRO (Bengaluru) career pages daily, matches against your
profile (Deputy Registrar / Administrative Officer / Purchase-Stores-Procurement
/ Level 10-12), and only surfaces **new** vacancies you haven't seen before.

## What you get
- **Daily automatic check** — no clicking required, runs on GitHub's free servers.
- **Telegram alert** for High/Medium relevance matches, the moment they appear.
- **A dashboard page** (`docs/index.html`, served via GitHub Pages) you can open
  any time to see everything found, old and new.

## One-time setup (about 15 minutes)

### 1. Create a GitHub repository
- Go to github.com → New repository → name it e.g. `vacancy-watcher` → Private is fine.
- Upload all the files in this folder to that repo (or `git init` + `git push`
  from your machine).

### 2. Enable GitHub Pages (for the dashboard)
- Repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`,
  folder: `/docs` → Save.
- Your dashboard will be live at `https://<your-username>.github.io/vacancy-watcher/`
  within a minute or two.

### 3. (Recommended) Set up Telegram alerts
- Message **@BotFather** on Telegram → `/newbot` → follow prompts → copy the
  **bot token** it gives you.
- Message your new bot anything (e.g. "hi") so it can message you back.
- Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
  find your **chat id** in the JSON response (`"chat":{"id": ...}`).
- In your repo: Settings → Secrets and variables → Actions → New repository secret:
  - `TELEGRAM_BOT_TOKEN` = the token from BotFather
  - `TELEGRAM_CHAT_ID` = your chat id

### 4. Turn on the schedule
- The workflow at `.github/workflows/daily-check.yml` is already configured to
  run every day at 9:00 AM IST, and can also be triggered manually any time
  from the repo's **Actions** tab → "Daily Vacancy Check" → "Run workflow".
- GitHub Actions is free for this volume of use on a private repo (well within
  the free minutes quota).

### 5. Check it worked
- Go to the **Actions** tab, run the workflow manually once.
- Check `docs/results.json` got updated, and your dashboard URL shows the run time.
- If you set up Telegram, you should get a message for any match found on the
  first run (the first run will likely surface several, since everything is "new").

## Tuning it to your profile
Edit `config.json`:
- `organizations` — add/remove/fix URLs. **Government sites restructure their
  careers pages every year or two** — if a page stops returning matches, open
  it in your browser first; the script will log a warning if it can't extract
  meaningful content.
- `keywords_any` — the terms that trigger a "candidate" line.
- `profile` — location, employer type, employment type, experience areas, and
  the pay-protection keyword flags used for scoring (High/Medium/Low).

## Important limits, honestly stated
- This does **keyword + heuristic matching** on page text, not true NLP — it
  will occasionally surface irrelevant lines or miss postings phrased unusually.
  Always verify against the actual PDF/advertisement before acting.
- Some organizations post vacancies only as scanned PDFs with no linked text on
  the listing page — for those (e.g. some ISRO centre PDFs), the script may see
  only a title/link, which is usually enough to catch new postings but won't
  extract post-level detail like pay level from the PDF itself. You'll need to
  open the PDF to confirm level/pay/last date.
- No system correctly identifies "pay protection" eligibility — that flag is
  just a keyword check (looks for "deputation", "pay protection", etc. in the
  listing) telling you it's *worth checking*, not a determination.
- If a site blocks automated requests entirely (some do via Cloudflare), that
  org's check will just log a fetch warning; you'd need to check it manually.
