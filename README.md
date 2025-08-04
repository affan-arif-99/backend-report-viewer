# Backend Report Viewer

This repository contains two main scripts:

- **extract.py**: Extracts data from an HTML report into a structured JSON file.
- **generate_pdf.py**: Uses [Playwright](https://playwright.dev/python/docs/intro) to load a web page and generate a PDF.

## Setup

1. **Clone the repository**

   ```sh
   git clone <your-repo-url>
   cd backend-report-viewer
   ```

2. **Create and activate a virtual environment**

   On Windows:

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

   On macOS/Linux:

   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```
   pip install -r requirements.txt
   ```

## **Usage**

Running extract.py```

The extract.py script reads an HTML report file, extracts key information using BeautifulSoup, and outputs the result into a JSON file

Usage:

```
python extract.py <input.html> > report.json
```

- Replace <input.html> with the path to your HTML report file.
- This `report.json` file should be placed inside the `public` directory in the frontend repo

Running `generate_pdf.py`

The generate_pdf.py script uses Playwright to navigate to a running web application (default URL is http://localhost:5173), apply print styles, and generate a PDF (saved as medical-report-ingested.pdf).

Usage:

Note: Ensure that your web application is running before executing this script.

```
python generate_pdf.py
```

Additional Notes
The virtual environment folder (venv) should be excluded from version control (see your .gitignore configuration).
All necessary package information is provided in the requirements.txt file.
