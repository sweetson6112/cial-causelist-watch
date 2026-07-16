"""
Kerala High Court Cause List Checker — CI/CD version
------------------------------------------------------
Runs the exact same workflow as the web app, but as a one-shot script
suitable for GitHub Actions:

  1. Check if https://highcourt.kerala.gov.in/ is reachable.
  2. Open the cause list search page on hckinfo.keralacourts.in.
  3. Select the requested date.
  4. Load the cause list results.
  5. Search for "COCHIN INTERNATIONAL AIRPORT" / "CIAL".
  6. If found -> download the PDF into data/pdfs/, else report no hit.

Writes:
  data/latest.json                 <- most recent run's result
  data/history/<date>.json         <- one file per date checked
  data/pdfs/<date>.pdf             <- downloaded cause list PDF, if any hit
  debug/<run_id>/*.png / *.html    <- troubleshooting snapshots (not committed;
                                       uploaded as a separate CI artifact)

See README.md for the same "selectors are best-guess" caveat as before —
nothing about that constraint changes just because this runs in CI instead
of on a server.
"""

import os
import sys
import json
import uuid
import argparse
import datetime
import traceback

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --------------------------------------------------------------------------
# CONFIG - adjust these if the live site's structure differs.
# Same selectors as the web-app version; tweak here if a run fails and the
# debug snapshot shows a different structure than expected.
# --------------------------------------------------------------------------

HIGH_COURT_HOME = "https://highcourt.kerala.gov.in/"
CAUSELIST_URL = "https://hckinfo.keralacourts.in/digicourt/Casedetailssearch/viewCauselist"

SEARCH_TERMS = ["cochin international airport", "cial"]

DATE_INPUT_SELECTORS = [
    "input[id*='date' i]",
    "input[name*='date' i]",
    "input.datepicker",
    "input[type='text'][placeholder*='date' i]",
    "input[type='date']",
]

SUBMIT_BUTTON_SELECTORS = [
    "button[id*='search' i]",
    "button[id*='submit' i]",
    "input[type='submit']",
    "button[type='submit']",
    "a[id*='search' i]",
    "button:has-text('Search')",
    "button:has-text('Submit')",
    "button:has-text('Go')",
]

RESULTS_CONTAINER_SELECTORS = [
    "table",
    "#resultsDiv",
    ".result-table",
    ".causelist-results",
    "div[id*='result' i]",
]

PDF_LINK_SELECTORS = [
    "a[href$='.pdf']",
    "a[href*='.pdf']",
    "a[id*='pdf' i]",
    "a[title*='pdf' i]",
    "button[id*='pdf' i]",
    "a:has-text('PDF')",
    "a:has-text('Download')",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
DEBUG_DIR = os.path.join(ROOT, "debug")

for d in (DATA_DIR, HISTORY_DIR, PDF_DIR, DEBUG_DIR):
    os.makedirs(d, exist_ok=True)


def check_site_reachable(url: str, timeout: int = 10) -> dict:
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CauseListChecker/1.0)"
        })
        return {"reachable": resp.status_code < 400, "status_code": resp.status_code}
    except requests.RequestException as e:
        return {"reachable": False, "status_code": None, "error": str(e)}


def _first_matching(page, selectors, timeout=4000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc, sel
        except PWTimeout:
            continue
        except Exception:
            continue
    return None, None


def save_debug(run_dir, page, label):
    os.makedirs(run_dir, exist_ok=True)
    try:
        page.screenshot(path=os.path.join(run_dir, f"{label}.png"), full_page=True)
    except Exception:
        pass
    try:
        with open(os.path.join(run_dir, f"{label}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass


def extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


def run_causelist_workflow(date_str: str, run_id: str) -> dict:
    run_dir = os.path.join(DEBUG_DIR, run_id)
    result = {
        "date": date_str,
        "run_id": run_id,
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "opened_page": False,
        "date_selected": False,
        "results_loaded": False,
        "hit": False,
        "matched_terms": [],
        "pdf_filename": None,
        "message": "",
    }

    try:
        y, m, d = date_str.split("-")
        date_variants = [f"{d}-{m}-{y}", f"{d}/{m}/{y}", f"{d}-{m}-{y[2:]}"]
    except Exception:
        date_variants = [date_str]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            page.goto(CAUSELIST_URL, timeout=30000, wait_until="domcontentloaded")
            result["opened_page"] = True
            save_debug(run_dir, page, "01_loaded")
        except Exception as e:
            result["message"] = f"Could not open cause list page: {e}"
            save_debug(run_dir, page, "01_load_failed")
            browser.close()
            return result

        date_input, _ = _first_matching(page, DATE_INPUT_SELECTORS)
        if date_input:
            filled = False
            for variant in date_variants:
                try:
                    date_input.click()
                    date_input.fill("")
                    date_input.fill(variant)
                    page.keyboard.press("Escape")
                    filled = True
                    break
                except Exception:
                    continue
            result["date_selected"] = filled
            save_debug(run_dir, page, "02_date_filled")
        else:
            result["message"] = (
                "Could not find a date input with the configured selectors. "
                "Check the debug artifact for this run and update "
                "DATE_INPUT_SELECTORS in scripts/check.py."
            )
            save_debug(run_dir, page, "02_no_date_input")
            browser.close()
            return result

        submit_btn, _ = _first_matching(page, SUBMIT_BUTTON_SELECTORS, timeout=3000)
        if submit_btn:
            try:
                submit_btn.click()
            except Exception as e:
                result["message"] = f"Found a submit button but couldn't click it: {e}"
        else:
            try:
                date_input.press("Enter")
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        results_el, _ = _first_matching(page, RESULTS_CONTAINER_SELECTORS, timeout=8000)
        save_debug(run_dir, page, "03_results")
        result["results_loaded"] = bool(results_el)
        if not results_el:
            result["message"] = (
                "Cause list results did not appear with the configured selectors. "
                "Check the debug artifact for what actually loaded."
            )

        page_text = page.content().lower()
        matched = [t for t in SEARCH_TERMS if t.lower() in page_text]

        pdf_link, _ = _first_matching(page, PDF_LINK_SELECTORS, timeout=3000)
        pdf_path = None
        if pdf_link:
            try:
                with page.expect_download(timeout=15000) as dl_info:
                    pdf_link.click()
                download = dl_info.value
                pdf_filename = f"{date_str}.pdf"
                pdf_path = os.path.join(PDF_DIR, pdf_filename)
                download.save_as(pdf_path)
            except Exception:
                pdf_path = None

        if pdf_path and os.path.exists(pdf_path):
            pdf_text = extract_pdf_text(pdf_path).lower()
            for term in SEARCH_TERMS:
                if term.lower() in pdf_text and term.lower() not in matched:
                    matched.append(term.lower())

        result["matched_terms"] = matched
        result["hit"] = len(matched) > 0

        if result["hit"]:
            if pdf_path and os.path.exists(pdf_path):
                result["pdf_filename"] = os.path.basename(pdf_path)
                result["message"] = f"Match found for: {', '.join(matched)}. PDF downloaded."
            else:
                result["message"] = (
                    f"Match found for: {', '.join(matched)}, but no PDF link could be "
                    "located automatically. Check the debug artifact and update "
                    "PDF_LINK_SELECTORS."
                )
        else:
            result["message"] = "No Cases mentioned for the day"

        browser.close()

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="", help="YYYY-MM-DD; blank = today")
    args = parser.parse_args()

    date_str = args.date.strip() or datetime.date.today().isoformat()
    run_id = uuid.uuid4().hex

    site_status = check_site_reachable(HIGH_COURT_HOME)
    output = {
        "date": date_str,
        "run_id": run_id,
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "site_status": site_status,
    }

    if not site_status["reachable"]:
        output["message"] = "Kerala High Court website appears to be down. Aborting."
        output["hit"] = False
    else:
        try:
            workflow_result = run_causelist_workflow(date_str, run_id)
            output.update(workflow_result)
        except Exception as e:
            output["error"] = f"Automation failed: {e}"
            output["trace"] = traceback.format_exc()
            output["message"] = "Automation crashed — see debug artifact / trace."
            output["hit"] = False

    # Write outputs
    with open(os.path.join(DATA_DIR, "latest.json"), "w") as f:
        json.dump(output, f, indent=2)
    with open(os.path.join(HISTORY_DIR, f"{date_str}.json"), "w") as f:
        json.dump(output, f, indent=2)

    print(json.dumps(output, indent=2))

    # Non-zero exit on hard failures helps surface problems in the Actions UI,
    # but a clean "no cases" result is a successful run, not a failure.
    if "error" in output:
        sys.exit(1)


if __name__ == "__main__":
    main()
