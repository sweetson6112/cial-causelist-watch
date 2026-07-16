# CIAL Cause List Watch — GitHub Actions Edition

Same workflow as before, but runs entirely on GitHub's free infrastructure
instead of a hosted server:

1. Checks whether `https://highcourt.kerala.gov.in/` is up.
2. If it's up, opens `https://hckinfo.keralacourts.in/digicourt/Casedetailssearch/viewCauselist`.
3. Selects a date (today by default, or one you choose).
4. Loads the cause list results.
5. Scans the results (and the cause list PDF, if produced) for
   **"COCHIN INTERNATIONAL AIRPORT"** or **"CIAL"** (case-insensitive).
6. If found — downloads the PDF and publishes a download link on the status page.
7. If not — the status page shows **"No Cases mentioned for the day."**

A GitHub Actions workflow runs the check (on a daily schedule, or on demand),
commits the result as JSON, and republishes a static status page via
GitHub Pages. No server, no memory limits to worry about, no cost.

---

## ⚠️ Same caveat as before — please read

`hckinfo.keralacourts.in` blocks automated crawlers via `robots.txt`, so I
could not load the real cause-list page while building this. The selectors
in `scripts/check.py` (date field, search button, results table, PDF link)
are written defensively with fallbacks, but are **best-guess** until tested
against the live site.

After your first run (manual or scheduled):

- Go to the **Actions** tab → open the run → download the
  `debug-<run_id>` artifact. It contains screenshots + full HTML at each
  step (`01_loaded`, `02_date_filled`, `03_results`, ...).
- If a step failed, find the real selector in that HTML and update the
  matching list near the top of `scripts/check.py`
  (`DATE_INPUT_SELECTORS`, `SUBMIT_BUTTON_SELECTORS`,
  `RESULTS_CONTAINER_SELECTORS`, `PDF_LINK_SELECTORS`).
- Commit and re-run. Expect one or two tuning rounds — normal for
  scraping a site you don't control.

---

## Setup

1. **Create a GitHub repo** and push this folder to it.

2. **Enable GitHub Pages**
   Repo → Settings → Pages → Source: **GitHub Actions** (not "Deploy from a
   branch" — the workflow already uses the official
   `actions/upload-pages-artifact` + `actions/deploy-pages` flow).

3. **Enable Actions** if prompted (Settings → Actions → Allow all actions).

4. **Run it once manually** to seed the site:
   Actions tab → **CIAL Cause List Check** → **Run workflow** → (optionally
   type a date as `YYYY-MM-DD`, or leave blank for today) → **Run workflow**.

5. After it finishes (2–4 minutes, mostly spent installing Chromium), your
   status page is live at:
   `https://<your-username>.github.io/<repo-name>/`

From then on it runs automatically every day at 03:30 UTC (09:00 IST) —
edit the `cron` line in `.github/workflows/check.yml` to change the time —
and you can always trigger an extra check for a specific date from the
Actions tab.

---

## Project layout

```
.github/workflows/check.yml   The workflow: run check → build site → commit data → deploy Pages
scripts/check.py               Standalone Playwright automation (no Flask)
scripts/build_site.py          Renders public/ from data/*.json
site_template/index.html       Static page template (stamp UI, history table)
data/latest.json               Most recent run's result (committed to the repo)
data/history/<date>.json       One file per date checked (committed to the repo)
data/pdfs/<date>.pdf           Downloaded cause list PDFs (committed to the repo)
requirements.txt
```

`debug/` and `public/` are git-ignored — they're regenerated every run and
published as either a Pages deployment or a downloadable Actions artifact,
not stored in the repo itself.

## Notes

- Every PDF hit gets committed to `data/pdfs/`, so your history builds up
  over time and stays browsable on the status page — nothing is overwritten
  between runs, only added to.
- If you'd rather not commit PDFs to git long-term (repo size), you can
  swap that step for uploading to a GitHub Release or external storage —
  ask if you'd like that version.
- Public repos get unlimited Actions minutes; private repos get 2,000
  free minutes/month, which comfortably covers a once-daily run.
