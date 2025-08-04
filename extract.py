#!/usr/bin/env python3
import sys, json
from bs4 import BeautifulSoup
import re

def extract_header(soup):
    hdr = {}
    # Participant info
    part_tbl = soup.find(id="Participant").find("table")
    rows = part_tbl.find_all("tr")
    hdr["name"]      = rows[0].find_all("td")[1].get_text(strip=True)
    hdr["createdOn"] = rows[1].find_all("td")[1].get_text(strip=True)
    # Practice info
    prac_tbl = soup.find(id="Practice").find("table")
    prow = prac_tbl.find_all("tr")
    hdr["doctor"] = prow[0].find_all("td")[1].get_text(strip=True)
    hdr["clinic"] = prow[1].find_all("td")[1].get_text(strip=True)
    # Static client label
    hdr["client"] = "uMETHOD"
    return hdr

def extract_preface(soup):
    header = extract_header(soup)

    # Purpose of This Report
    purpose_ps = []
    for p in soup.select("#Purpose p"):
        purpose_ps.append(p.get_text(" ", strip=True))
    statistic = next((s for p in purpose_ps for s in p.split(". ") if "%" in s), "")

    # About RestoreU METHOD
    about_ps = [p.get_text(" ", strip=True) for p in soup.select("#About p")]

    # Reading This Report
    # intro = [p.get_text(" ", strip=True) for p in soup.select("#Reading > p")]
    # steps = [li.get_text(" ", strip=True) for li in soup.select("#Reading ol > li")]
    # Reading This Report
    reading_h2 = soup.find("h2", id="ShdMrpReading")
    # grab the two intro <p>
    intro = [p.get_text(" ", strip=True) 
             for p in reading_h2.find_next_siblings("p", limit=2)]

    # grab the three <li> descriptions
    ol = reading_h2.find_next_sibling("ol")
    descriptions = [li.get_text(" ", strip=True) for li in ol.find_all("li")]

    # static titles in the desired order
    titles = [
      "Overview of Risk Factors",
      "Personalized Action Plan",
      "In-Depth Insights"
    ]

    # combine into step objects
    steps = [
      {"title": titles[i], "description": descriptions[i]}
      for i in range(len(descriptions))
    ]


    return {
        "header": header,
        "title": "Preface",
        "purposeParagraphs": purpose_ps,
        "statisticCallout": statistic,
        "aboutParagraphs": about_ps,
        "reading": {
            "intro": intro,
            "steps": steps
        }
    }

def extract_health_report(soup):
    header = extract_header(soup)

    # Overview table under “YourStatus”
    status_tbl = soup.select_one("#YourStatus table")
    ths = [th.get_text(strip=True) for th in status_tbl.find_all("th")]
    tds = status_tbl.find_all("td")

    overview = {}
    for h, td in zip(ths, tds):
        # base value = all text nodes except those inside <small>
        base = "".join(
            t for t in td.contents
            if isinstance(t, str)
        ).strip()
        # collect every <small> text, strip punctuation
        ann = [s.get_text(strip=True).strip("() ") for s in td.find_all("small")]

        key = "".join(ch for ch in h if ch.isalnum())
        overview[key] = {
            "value": base,
            "annotations": ann
        }

    # Health-Status sections extraction remains unchanged…
    sections = []  # same as before

    gyrg = None
    for tbl in soup.find_all("table"):
        if tbl.find("td", class_=lambda c: c and "tdBackground" in c and c.endswith("Left")):
            gyrg = tbl
            break

    if gyrg:
        rows = gyrg.find_all("tr", recursive=False)
        i = 0
        title_map = {
            "Green": "Optimal",
            "Yellow": "Caution",
            "Red": "At Risk",
            "Gray": "Unknown"
        }
        while i < len(rows):
            hdr_row = rows[i]
            hdr_td = hdr_row.find("td", class_=lambda c: c and "tdBackground" in c and c.endswith("Left"))
            if hdr_td:
                raw = hdr_td.get_text(" ", strip=True)
                # e.g. "Green: These factors..."
                key = hdr_td.find("i").get_text(strip=True).rstrip(":")
                title = title_map.get(key, key)
                desc = raw.split(":", 1)[1].strip()

                # next row holds the bullet list
                factors = []
                if i+1 < len(rows):
                    content_td = rows[i+1].find("td")
                    nested = content_td.find("table", class_="no_border")
                    if nested:
                        for tr in nested.find_all("tr"):
                            for td in tr.find_all("td"):
                                text = td.get_text(" ", strip=True)
                                if text.startswith("•") or text.startswith("\u2022"):
                                    factors.append(text.lstrip("• ").strip())

                sections.append({
                    "title": title,
                    "count": len(factors),
                    "description": desc,
                    "factors": factors
                })
                i += 2
            else:
                i += 1

    return {
        "header": header,
        "title": "Current Status",
        "currentStatus": { "overview": overview },
        "healthStatusSections": sections
    }

def extract_action_plan(soup):
    ap = {}
    # Locate the main ActionPlan container
    ap_div = soup.find("div", id="ActionPlan")
    if not ap_div:
        return None

    # Title
    title_tag = ap_div.find("h1", id="ShdMrpActionPlan")
    ap["title"] = title_tag.get_text(" ", strip=True) if title_tag else "Your Action Plan"

    # Intro paragraphs
    ap["intro"] = [
        p.get_text(" ", strip=True)
        for p in ap_div.find_all("p", recursive=False)
    ]

    # Bullet-list steps
    first_ul = ap_div.find("ul")
    ap["steps"] = [
        li.get_text(" ", strip=True).rstrip(",")
        for li in first_ul.find_all("li")
    ] if first_ul else []

    # Medications table
    meds = []
    meds_hdr = soup.find("h3", id="ShdMrpMedsPrescriptions")
    if meds_hdr:
        meds_table = meds_hdr.find_next("table")
        # iterate each data row
        for row in meds_table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            # Basic columns
            medication    = cols[0].get_text(" ", strip=True)
            dosageDetails = cols[1].get_text(" ", strip=True)
            alreadyTaking = cols[2].get_text(" ", strip=True)
            guidance      = cols[4].get_text(" ", strip=True)

            # --- Parse reasoning column into structured entries ---
            reasoning_td = cols[3]
            # get text with explicit separators for <br>
            text = reasoning_td.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            reasoning_entries = []
            current_action = None
            for line in lines:
                # lines ending with ':' are the action label
                if line.endswith(":"):
                    current_action = line.rstrip(":")
                # bullet lines start with '•' or '-' or digits
                elif line.startswith("•") or line.startswith("-"):
                    bullet = line.lstrip("•- ").strip()
                    # split name and level in parentheses
                    m = re.match(r"(.+?)\s*\((.+)\)", bullet)
                    if m:
                        name, level = m.groups()
                    else:
                        name, level = bullet, ""
                    reasoning_entries.append({
                        "action": current_action or "",
                        "name": name.strip(),
                        "currentLevel": level.strip()
                    })
                else:
                    m2 = re.match(r"(.+?)\s*\((.+)\)\.?", line)
                    if m2:
                        action_text, usage = m2.groups()
                        reasoning_entries.append({
                            "action": action_text.strip(),
                            "currentUsage": usage.strip()
                        })
                    else:
                        # fallback: treat any other non-bullet line as a new action
                        reasoning_entries.append({
                            "action": line,
                            "currentUsage": ""
                        })

            meds.append({
                "medication":    medication,
                "dosageDetails": dosageDetails,
                "alreadyTaking": alreadyTaking,
                "reasoning":     reasoning_entries,
                "guidance":      guidance
            })

    ap["medications"] = meds
    return ap


def main(path):
    # Read as raw bytes so BeautifulSoup can detect encoding
    with open(path, 'rb') as f:
        raw = f.read()

    # Let BeautifulSoup handle the decoding
    soup = BeautifulSoup(raw, 'html.parser')

    report = {
        "preface": extract_preface(soup),
        "healthReport": extract_health_report(soup),
        "actionPlan": extract_action_plan(soup)
    }
    with open("report.json", "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)

    print("✅ Wrote report.json")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scrape_report.py <input.html>")
        sys.exit(1)
    main(sys.argv[1])
