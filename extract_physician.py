import time
import os
import json
from bs4 import BeautifulSoup

def extract_preface(soup: BeautifulSoup) -> dict:
    return {
        "title": "",
        "intro": ""
    }

OUTPUT_DIR     = "output"
HTML_FILE      = "Physician_Summary_1-00_JANEADOE_2024-11-02.html"
REPORT_JSON    = os.path.join(OUTPUT_DIR, "report_physician.json")

def main(path: str = HTML_FILE, output: str = REPORT_JSON):
    # Read as raw bytes so BeautifulSoup can detect encoding
    with open(path, 'rb') as f:
        raw = f.read()

    # Let BeautifulSoup handle the decoding
    soup = BeautifulSoup(raw, 'html.parser')

    report = {
        "preface": extract_preface(soup),
        # "supplements":  extract_supplements(soup),
        # "lifestyle": extract_lifestyle(soup)
    }
    with open(output, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)


if __name__ == "__main__":
    total_start = time.perf_counter()

    # 1) build JSON
    start = time.perf_counter()
    main()
    print(f"✅ extract_data: {time.perf_counter() - start:.2f}s")
