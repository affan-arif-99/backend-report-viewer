#!/usr/bin/env python3
"""
run_report.py

1) Parse the HTML into report.json in dist/
2) Serve dist/ on localhost:8000
3) Spin up Playwright and snapshot the PDF
"""

import os
import sys
import json
import re
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from extract_patient import extract_preface, extract_health_report, extract_action_plan
# —— CONFIG —————————————————————————————————————————————————————————————
DIST_DIR       = "dist"
HTML_FILE      = "Report_Participant_1-00_JANEADOE_2024-11-02.html"
REPORT_JSON    = os.path.join(DIST_DIR, "report.json")
PDF_OUTPUT     = "medical-report.pdf"
HOST, PORT     = "0.0.0.0", 5173
URL            = f"http://localhost:{PORT}"
# URL            = f"https://www.nytimes.com/projects/2012/snow-fall/"

# —— EXTRACTION LOGIC (inlined from extract.py) ————————————————————————

def build_report():
    """Parses the HTML and writes report.json inside dist/"""
    html = open(HTML_FILE, "rb").read()
    soup = BeautifulSoup(html, "html.parser")
    report = {
        "preface":        extract_preface(soup),
        "healthReport":   extract_health_report(soup),
        "actionPlan":     extract_action_plan(soup)
    }
    # json.dump(report, f, indent=2) should dump inside existing dist/
    os.makedirs(DIST_DIR, exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"✅ Wrote {REPORT_JSON}")

# —— SERVER LOGIC ——————————————————————————————————————————————————————————

def serve_dist():
    os.chdir(DIST_DIR)
    srv = HTTPServer((HOST, PORT), SimpleHTTPRequestHandler)
    print(f"🚀 Serving {DIST_DIR} at http://localhost:{PORT}")
    srv.serve_forever()

# —— PDF GENERATION (inlined from generate_pdf.py) ——————————————————————

FOOTER_TMPL = """
<div style="
    font-size: 10px;
    color: #6B7280;      /* Tailwind text-gray-500 */
    padding-left: 58px;
    padding-right: 58px;
    width: 100%;
    box-sizing: border-box;
">
    <div style="
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    width: 100%;
    ">
    <div style="line-height: 1.2;">
        <div>uMETHOD Health, Inc.</div>
        <div>9650 Falls of Neuse Road, Suite 138‑146</div>
        <div>Raleigh, NC 27615</div>
        <div style="color: #3B82F6;">support@umethod.com</div>
    </div>
    <div style="text-align: right; line-height: 1.2;">
        <div>Copyright © 2013‑2025 uMETHOD Health, Inc.</div>
        <div>All Rights Reserved. Confidential.</div>
    </div>
    </div>
    <div style="
    text-align: center;
    margin-top: 4mm;
    font-size: 9px;
    ">
    <span class="pageNumber"></span> / <span class="totalPages"></span>
    </div>
</div>
"""
def generate_pdf():
    print(f"📑 Generating PDF from {URL} …")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page    = browser.new_page(viewport={"width":1200,"height":1600})
        page.emulate_media(media="print")
        page.goto(URL, wait_until="networkidle")
        # zero-margin
        page.add_style_tag(content="""
          @page { size: A4; margin-top: 0 !important; }
        """)
        page.pdf(
            path=PDF_OUTPUT,
            format="A4",
            print_background=True,
            margin={"top":"0mm","bottom":"1mm","left":"0mm","right":"0mm"},
            prefer_css_page_size=True,
            display_header_footer=True,
            footer_template=FOOTER_TMPL
        )
        browser.close()
    print(f"✅ PDF saved as {PDF_OUTPUT}")

# —— MAIN ORCHESTRATION ——————————————————————————————————————————————

import threading
import time

if __name__ == "__main__":
    total_start = time.perf_counter()

    # # 1) build JSON
    start = time.perf_counter()
    build_report()
    print(f"✅ build_report: {time.perf_counter() - start:.2f}s")

    # # 2) serve in background
    start = time.perf_counter()
    t = threading.Thread(target=serve_dist, daemon=True)
    t.start()
    time.sleep(1)
    print(f"✅ serve_dist startup + sleep: {time.perf_counter() - start:.2f}s")

    # 3) generate PDF
    start = time.perf_counter()
    generate_pdf()
    print(f"✅ generate_pdf: {time.perf_counter() - start:.2f}s")

    print(f"🎉 Total script time: {time.perf_counter() - total_start:.2f}s")
