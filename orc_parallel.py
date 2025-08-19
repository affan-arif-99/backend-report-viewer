#!/usr/bin/env python3
import os
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from extract import extract_preface, extract_health_report, extract_action_plan
from generate_pdf import main as generate
from extract import main as extract

# —— CONFIG —————————————————————————————————————————————————————————————
DIST_DIR       = "output"
HTML_FILE      = "Report_Participant_1-00_JANEADOE_2024-11-02.html"
REPORT_JSON    = os.path.join(DIST_DIR, "report.json")
PDF_OUTPUT     = "medical-report.pdf"  # All threads will write to this file
BUILD_PATH     = "file:///dist/index.html"
HOST, PORT     = "0.0.0.0", 5173
URL            = f"http://localhost:{PORT}"

# —— EXTRACTION LOGIC (inlined from extract.py) ————————————————————————
def build_report():
    """Parses the HTML and writes report.json inside dist/"""
    print(f"⏳ Parsing {HTML_FILE}")
    extract(HTML_FILE, REPORT_JSON)
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
    color: #6B7280;
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

def generate_pdf(build_path, pdf_output):
    print(f"📑 Generating PDF from {build_path} …")
    generate(build_path, pdf_output, FOOTER_TMPL)
    print(f"✅ PDF saved as {pdf_output}")

# —— MAIN ORCHESTRATION ——————————————————————————————————————————————
import threading
import time

if __name__ == "__main__":
    total_start = time.perf_counter()

    if not os.path.exists("output"):
        os.makedirs("output")
    
    # Uncomment these steps if needed:
    build_report()
    # t = threading.Thread(target=serve_dist, daemon=True)
    # t.start()
    # time.sleep(1)

    # Run generate_pdf in parallel on 2 threads with unique PDF_OUTPUT names
    threads = []
    for i in range(2):
        pdf_file = os.path.join(DIST_DIR, f"medical-report_{i+1}.pdf")
        t = threading.Thread(target=generate_pdf, args=(BUILD_PATH, pdf_file,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"🎉 Total script time: {time.perf_counter() - total_start:.2f}s")