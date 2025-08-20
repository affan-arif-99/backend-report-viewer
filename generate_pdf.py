# generate_pdf.py
from playwright.sync_api import sync_playwright

def main(input_path: str, output_filename: str, footer_tmpl: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--allow-running-insecure-content",
                "--allow-file-access-from-files"   # allows file:// requests
            ]
        )
        page = browser.new_page(viewport={"width":1200, "height":1600})

         # Log every request
        page.on("request", lambda request: print(f"➡️ {request.method} {request.url}"))

        # Log every response
        page.on("response", lambda response: print(f"⬅️ {response.status} {response.url}"))
        
        page.on("console", lambda msg: print(f"[browser console] {msg.type}: {msg.text}"))
    
        # 1. Emulate print so @page rules will be applied
        page.emulate_media(media="print")
        
        # 2. Navigate and wait for your app’s CSS to settle
        page.goto(input_path, wait_until="networkidle")
        # page.goto("http://localhost:5173", wait_until="networkidle")

        # 3. Inject zero‑margin @page rules *after* navigation
        page.add_style_tag(content="""
          @page { size: A4; margin-top: 0 !important; }
        """)
        
        # 5. Export with zero margins
        page.pdf(
            path=output_filename,
            format="A4",
            print_background=True,
            margin={"top":"0mm","bottom":"1mm","left":"0mm","right":"0mm"},
            prefer_css_page_size=True,
            display_header_footer=True,
            footer_template=footer_tmpl
        )

        browser.close()

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