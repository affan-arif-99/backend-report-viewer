#!/usr/bin/env python3
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from extract_patient import extract_preface, extract_health_report, extract_action_plan
from generate_pdf import main as generate
from extract_patient import main as extract_patient
from extract_physician import main as extract_physician


# —— CONFIG —————————————————————————————————————————————————————————————
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
OUTPUT_DIR       = "output"
PARTICIPANT_HTML_FILE      = "Report_Participant_1-00_JANEADOE_2024-11-02.html"
PHYSICIAN_HTML_FILE      = "Physician_Summary_1-00_JANEADOE_2024-11-02.html"
PDF_OUTPUT     = "medical-report.pdf"  # All threads will write to this file
BUILD_PATH     = os.path.abspath("dist/index.html")
PARTICIPANT_REPORT_TYPE    = "participant"
PHYSICIAN_REPORT_TYPE      = "physician"
HOST, PORT     = "0.0.0.0", 5173
URL            = f"http://{HOST}:{PORT}"
def get_report_url(path=""):
    return f"{URL}/{path.lstrip('/')}"

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
        <a href="mailto:support@umethod.com">support@umethod.com</a>
    </div>
    <div style="text-align: right; line-height: 1.2;">
        <div>Copyright © 2013–2025 uMETHOD Health, Inc.</div>
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

# —— EXTRACTION LOGIC (inlined from extract.py) ————————————————————————
def build_report(type: str = PARTICIPANT_REPORT_TYPE):
    HTML_FILE = PARTICIPANT_HTML_FILE if type == PARTICIPANT_REPORT_TYPE else PHYSICIAN_HTML_FILE
    REPORT_JSON = os.path.join(OUTPUT_DIR, f"report_{type}.json")

    if type == PARTICIPANT_REPORT_TYPE:
        """Parses the HTML and writes report.json inside dist/"""
        print(f"⏳ Parsing {HTML_FILE}")
        extract_patient(HTML_FILE, REPORT_JSON)
        print(f"✅ Wrote {REPORT_JSON}")
    elif type == PHYSICIAN_REPORT_TYPE:
        """Parses the HTML and writes report.json inside dist/"""
        print(f"⏳ Parsing {HTML_FILE}")
        extract_physician(HTML_FILE, REPORT_JSON)
        print(f"✅ Wrote {REPORT_JSON}")

# —— SERVER MANAGEMENT ——————————————————————————————————————————————————
class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        clean_path = parsed.path.lstrip("/")
        requested_path = os.path.join(DIST_DIR, clean_path)

        if os.path.isfile(requested_path):
            # Serve static file with cache headers
            super().do_GET()
        else:
            # Fallback → serve index.html with no-cache
            fallback = os.path.join(DIST_DIR, "index.html")
            print(f"Fallback: {self.path} → /index.html")

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with open(fallback, "rb") as f:
                self.wfile.write(f.read())

    def end_headers(self):
        """Add cache headers to static assets before finalizing response"""
        if self.path.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2")):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        return super().end_headers()

def start_server():
    """Start HTTP server in background thread"""
    httpd = ThreadingHTTPServer((HOST, PORT), CustomHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"🚀 Serving {DIST_DIR} at {URL}")
    return httpd, thread

def stop_server(httpd):
    """Stop HTTP server cleanly"""
    print("🛑 Stopping server...")
    httpd.shutdown()
    httpd.server_close()

# —— PDF GENERATION (inlined from generate_pdf.py) ——————————————————————
def generate_pdf(build_path, pdf_output):
    print(f"📑 Generating PDF from {build_path} …")
    generate(build_path, pdf_output, FOOTER_TMPL)
    print(f"✅ PDF saved as {pdf_output}")

# —— MAIN ORCHESTRATION ——————————————————————————————————————————————
if __name__ == "__main__":
    total_start = time.perf_counter()

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Step 1. Build report.json
    threads = []
    reports = [PARTICIPANT_REPORT_TYPE, PHYSICIAN_REPORT_TYPE]
    for report_type in reports:
        t = threading.Thread(target=build_report, args=(report_type,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()

    # Step 2. Start server
    httpd, server_thread = start_server()

    # Step 3. Run PDF generation in parallel
    threads = []
    reports = [
        (get_report_url(PARTICIPANT_REPORT_TYPE), os.path.join(OUTPUT_DIR, "medical-report_participant.pdf")),
        (get_report_url(PHYSICIAN_REPORT_TYPE), os.path.join(OUTPUT_DIR, "medical-report_physician.pdf"))
    ]

    for html_file, pdf_file in reports:
        t = threading.Thread(target=generate_pdf, args=(html_file, pdf_file))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Step 4. Stop server
    stop_server(httpd)

    print(f"🎉 Total script time: {time.perf_counter() - total_start:.2f}s")