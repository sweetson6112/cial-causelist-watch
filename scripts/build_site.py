"""
Builds the static site in public/ from the JSON files in data/.
Run after scripts/check.py so data/latest.json and data/history/*.json exist.
"""

import os
import json
import glob
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
PUBLIC_DIR = os.path.join(ROOT, "public")


def load_history():
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")), reverse=True)
    runs = []
    for f in files:
        try:
            with open(f) as fh:
                runs.append(json.load(fh))
        except Exception:
            continue
    return runs


def main():
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    os.makedirs(os.path.join(PUBLIC_DIR, "pdfs"), exist_ok=True)

    latest_path = os.path.join(DATA_DIR, "latest.json")
    latest = {}
    if os.path.exists(latest_path):
        with open(latest_path) as f:
            latest = json.load(f)

    history = load_history()

    # Copy any PDFs into the public folder so they're servable by Pages.
    for pdf in glob.glob(os.path.join(PDF_DIR, "*.pdf")):
        shutil.copy(pdf, os.path.join(PUBLIC_DIR, "pdfs", os.path.basename(pdf)))

    with open(os.path.join(PUBLIC_DIR, "latest.json"), "w") as f:
        json.dump(latest, f, indent=2)
    with open(os.path.join(PUBLIC_DIR, "history.json"), "w") as f:
        json.dump(history, f, indent=2)

    # .nojekyll avoids GitHub Pages' Jekyll processing mangling anything.
    open(os.path.join(PUBLIC_DIR, ".nojekyll"), "w").close()

    shutil.copy(os.path.join(ROOT, "site_template", "index.html"),
                os.path.join(PUBLIC_DIR, "index.html"))

    print(f"Built site: latest run {latest.get('date')} — hit={latest.get('hit')}")
    print(f"History entries: {len(history)}")


if __name__ == "__main__":
    main()
