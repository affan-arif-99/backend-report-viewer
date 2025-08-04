# generate_pdf.py
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width":1200, "height":1600})

        # 1. Emulate print so @page rules will be applied
        page.emulate_media(media="print")

        # 2. Navigate and wait for your app’s CSS to settle
        page.goto("http://localhost:5173", wait_until="networkidle")

        # 3. Inject zero‑margin @page rules *after* navigation
        page.add_style_tag(content="""
          @page { size: A4; margin-top: 0 !important; }
        """)

        # 5. Export with zero margins
        page.pdf(
            path="medical-report-ingested.pdf",
            format="A4",
            print_background=True,
            margin={"top":"0mm","bottom":"1mm","left":"0mm","right":"0mm"},
            prefer_css_page_size=True,
            display_header_footer=True,
            footer_template="""
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
        )

        browser.close()
    print("✅ PDF saved as medical-report.pdf")

if __name__ == "__main__":
    main()



# with sync_playwright() as p:
    #     browser = p.chromium.launch()
    #     page = browser.new_page()
    #     # point at your running React app
    #     page.set_viewport_size({"width": 1200, "height": 800})
    #     page.emulate_media(media="screen")
    #     page.goto("http://localhost:5173", wait_until="networkidle")
    #     # adjust margins or header/footer here if you like
    #     page.pdf(
    #         path="medical-report.pdf",
    #         format="A4",
    #         print_background=True,
    #         margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
    #         prefer_css_page_size=True,
    #         display_header_footer=False,
    #     )
    #     browser.close()