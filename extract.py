#!/usr/bin/env python3
import json
import re
import time

from bs4 import BeautifulSoup, Tag, NavigableString

NBSP = "\xa0"
BULLET_CHARS = ("•", "\u2022")

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

    supplements_title_tag = soup.find("h3", id="ShdMrpMedsSupplements")
    ap["supplements"] = {}
    ap["supplements"]["title"] = supplements_title_tag.get_text(" ", strip=True) if supplements_title_tag else "Supplements"
    
    ap["supplements"]["intro"] = []
    supplements_intro = supplements_title_tag.find_next("div").find("p")
    supplements_intro = supplements_intro.get_text(" ", strip=True) if supplements_intro else ""
    supplements_intro = [line.strip() for line in supplements_intro.split(".") if line.strip()]
    ap["supplements"]["intro"] = supplements_intro

    ap["supplements"]["meds"] = []
    if supplements_title_tag:
        supplements_table = supplements_title_tag.find_next("table")
        # iterate each data row
        for row in supplements_table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            # Basic columns
            medication    = cols[0].get_text(" ", strip=True)
            dosageDetails = cols[1].get_text(" ", strip=True)
            guidance      = cols[3].get_text(" ", strip=True)

            # --- Parse reasoning column into structured entries ---
            reasoning_td = cols[2]
            # get text with explicit separators for <br>
            text = reasoning_td.get_text(separator="\n\r", strip=True)
            current_action, reasons = text.split(":", 1) if ":" in text else [text, ""]
            lines = [line.strip() for line in reasons.split("\n\r") if line.strip()]

            reasoning_entries = []
            for line in lines:
                # bullet lines start with '•' or '-' or digits
                if line.startswith("•") or line.startswith("-"):
                    bullet = line.lstrip("•- ").strip()
                    # split name and level in parentheses
                    m = re.match(r"(.+?)\s*\((.+)\)", bullet)
                    if m:
                        name, level = m.groups()
                    else:
                        name, level = bullet, ""
                    reasoning_entries.append({
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

            ap["supplements"]["meds"].append({
                "medication":    medication,
                "dosageDetails": dosageDetails,
                "reasoning": {
                    "action": current_action,
                    "entries": reasoning_entries
                },
                "guidance":      guidance
            })
    

    return ap

def extract_current_medication(soup):
    current_medication = {}
    medications = soup.find("div", id="Medications")
    current_medication_title = medications.find("h3", id="ShdMrtMedsCurrent")
    current_medication["title"] = current_medication_title.get_text(" ", strip=True) if current_medication_title else "Current Medication"
    
    current_medication_intro = current_medication_title.find_next("p")
    current_medication["intro"] = current_medication_intro.get_text(" ", strip=True) if current_medication_intro else ""
    
    current_medication_table = current_medication_title.find_next("table") if current_medication_title else None
    meds = []
    headers = []
    if current_medication_table:
        # Extract headers
        headers = [th.get_text(" ", strip=True) for th in current_medication_table.find_all("th")]
        # Extract rows
        for row in current_medication_table.find_all("tr")[1:]:  # skip header row
            cols = row.find_all("td")
            if len(cols) == 4:
                medication = cols[0].get_text(" ", strip=True)
                dosage_details = cols[1].get_text(" ", strip=True)
                indication = cols[2].get_text(" ", strip=True)
                date_started = cols[3].get_text(" ", strip=True)
                meds.append({
                    "medication": medication,
                    "dosageDetails": dosage_details,
                    "indication": indication,
                    "dateStarted": date_started
                })
    current_medication["headers"] = headers
    current_medication["medications"] = meds
    return current_medication

def extract_lifestyle(soup):
    lifestyle = {}
    lifestyle_title_tag = soup.find("h2", id="ShdMrpLifestyle")
    lifestyle["title"] = lifestyle_title_tag.get_text(" ", strip=True)

    lifestyle_intro = lifestyle_title_tag.find_next("div").find("p")
    lifestyle_intro = lifestyle_intro.get_text(" ", strip=True) if lifestyle_intro else ""
    # lifestyle_intro = [line.strip() for line in lifestyle_intro.split(".") if line.strip()]
    lifestyle["intro"] = lifestyle_intro
    
    lifestyle["recommendations"] = []

    # Find the recommendations table after the lifestyle_title_tag
    recommendations_table = lifestyle_title_tag.find_next("table")
    if recommendations_table:
        # Skip the header row (first <tr>)
        for tr in recommendations_table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            # Extract area text, image name (if present), and area title
            area_img = tds[0].find("img")
            area_image = area_img["src"] if area_img and area_img.has_attr("src") else None
            area_title = tds[0].get_text(" ", strip=True)
            area = {
                "title": area_title,
                "image": area_image
            }
            task = tds[1].get_text(" ", strip=True)
            instructions_text = tds[2].get_text(" ", strip=True)
            # Split by full stop, remove empty entries, strip whitespace
            instructions = [instr.strip() for instr in instructions_text.split('.') if instr.strip()]
            lifestyle["recommendations"].append({
                "area": area,
                "task": task,
                "instructions": instructions
            })
    return lifestyle

def extract_nutrition(soup):
    nutrition = {}
    nutrition["recommendations"] = {}
    nutrition_header = soup.find("h2", id="ShdMrpNewDiet")
    nutrition["recommendations"]["header"] = nutrition_header.get_text(" ", strip=True)
    
    nutrition_header_intro = nutrition_header.find_next("p")
    nutrition["recommendations"]["header_intro"] = nutrition_header_intro.get_text(" ", strip=True) if nutrition_header_intro else ""
    
    mind_diet_title = soup.find("h3", id="ShdMrpMINDDiet")
    nutrition["mind_diet_title"] = mind_diet_title.get_text(" ", strip=True) if mind_diet_title else "MIND Diet"
    mind_diet_intro = mind_diet_title.find_next("div").find("p")
    nutrition["recommendations"]["mind_diet_intro"] = mind_diet_intro.get_text(" ", strip=True) if mind_diet_intro else ""
    
    recommended_instructions = mind_diet_intro.find_next("p")
    nutrition["recommendations"]["recommended_instructions"] = recommended_instructions.get_text(" ", strip=True) if recommended_instructions else ""
    
    recommended_diet = {
        "headers": [],
        "entries": []
    }
    recommended_diet_table = mind_diet_title.find_next("table")
    if recommended_diet_table:
        headers = [th.get_text(" ", strip=True) for th in recommended_diet_table.find_all("th")]
        recommended_diet["headers"] = headers
        rows = recommended_diet_table.find_all("tr")[1:]  # skip header row
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 2:
                food_group = cols[0].get_text(" ", strip=True)
                frequency = cols[1].get_text(" ", strip=True)
                recommended_diet["entries"].append({
                    "foodGroup": food_group,
                    "frequency": frequency
                })
    nutrition["recommendations"]["recommended_diet"] = recommended_diet
    
    # Discouraged Foods Section
    discouraged_instructions = recommended_diet_table.find_next("p")
    nutrition["recommendations"]["discouraged_instructions"] = discouraged_instructions.get_text(" ", strip=True) if discouraged_instructions else "Discouraged Foods"

    discouraged_table = discouraged_instructions.find_next("table") if discouraged_instructions else None
    discouraged_diet = {
        "headers": [],
        "entries": []
    }
    if discouraged_table:
        discouraged_diet["headers"] = [th.get_text(" ", strip=True) for th in discouraged_table.find_all("th")]
        for row in discouraged_table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) == 2:
                food_group = cols[0].get_text(" ", strip=True)
                frequency = cols[1].get_text(" ", strip=True)
                discouraged_diet["entries"].append({
                    "foodGroup": food_group,
                    "frequency": frequency
                })
    nutrition["recommendations"]["discouraged_diet"] = discouraged_diet
    
    nutrition["summary"] = {}
    summary_title = discouraged_table.find_next("h2")
    nutrition["summary"]["title"] = summary_title.get_text(" ", strip=True) if summary_title else "Summary"
    
    outer_table = summary_title.find_next("table")
    warning = outer_table.find("td").contents[0]
    
    nutrition["summary"]["warning"] = warning.get_text(" ", strip=True) if warning else ""
    
    nutrition["summary"]["deficiencies"] = []
    inner_tables = outer_table.find_all("table")
    for idx, row in enumerate(inner_tables):
        # print("Table", row)
        
        deficiency = {}
        if idx % 2 == 0:
            # Even index rows are first column
            nutrient_text = row.find_all("td")[2].get_text(" ", strip=True)
            deficiency["nutrient"] = nutrient_text.split(",")[0].strip().strip(":")
            deficiency["normal_range"] = nutrient_text.split(",")[1].strip().strip(":") if len(nutrient_text.split(",")) > 1 else ""
        else:
            # Odd index rows are second column
            deficiency["result"] = {}
            result_col = row.find_all("td")[2]
            result_text = result_col.get_text(" ", strip=True)
            # Extract nutrient_sub (text in round brackets)
            nutrient_sub_match = re.search(r"\(([^)]+)\)", result_text)
            nutrient_sub = nutrient_sub_match.group(1) if nutrient_sub_match else ""
            # Remove nutrient_sub from result_text
            if nutrient_sub:
                result_text = result_text.replace(f"({nutrient_sub})", "").strip()
                
            # Extract reading (number + units)
            reading_match = re.search(r"(?<![a-zA-Z])\b(\d+(?:\.\d+)?\s*\w*)\b", result_text)
            reading = reading_match.group(1) if reading_match else ""
            # Remove reading from desc
            result_text = result_text.replace(reading, "").strip()
            # Extract severity
            severity_match = re.match(r"(very high|high|low|very low)", result_text, re.IGNORECASE)
            severity = severity_match.group(1).lower() if severity_match else ""
            # Remove severity from text
            result_text = re.sub(r"^(very high|high|low|very low)\s*", "", result_text, flags=re.IGNORECASE)


            deficiency["result"]["severity"] = severity
            deficiency["result"]["desc"] = result_text.strip()
            deficiency["result"]["reading"] = reading
            deficiency["nutrient_sub"] = nutrient_sub

        # Only append if index does not exist in deficiencies array
        if idx % 2 == 0:
            nutrition["summary"]["deficiencies"].append(deficiency)
        else:
            nutrition["summary"]["deficiencies"][len(nutrition["summary"]["deficiencies"]) - 1] = {**nutrition["summary"]["deficiencies"][len(nutrition["summary"]["deficiencies"]) - 1], **deficiency}

    consumption = {}
    advice = outer_table.find_next("p")
    consumption["advice"] = advice.get_text(" ", strip=True) if advice else ""
    consumption_table_outer = advice.find_next("table")
    consumption_title = consumption_table_outer.find("td").contents[0]
    consumption["title"] = consumption_title.get_text(" ", strip=True) if consumption_title else "Dietary Consumption Summary"

    consumption["entries"] = []
    consumption_table_inner = consumption_table_outer.find("table")
    for idx, row in enumerate(consumption_table_inner.find_all("tr")[0:]):
        entry = {}
        # print("Row", row)
        # Extract nutrient name
        consumption_group = row.find_all("td")[2]
        entry["group"] = consumption_group.get_text(" ", strip=True).split(":")[0].strip() if consumption_group else ""
        entry["intake"] = consumption_group.get_text(" ", strip=True).split(":")[1].strip() if consumption_group and ":" in consumption_group.get_text(" ", strip=True) else ""

        # Extract nutrient value
        note = row.find_all("td")[4]
        entry["note"] = note.get_text(" ", strip=True) if note else ""

        consumption["entries"].append(entry)
        
    nutrition["consumption"] = consumption
    
    return nutrition

def extract_cognitive_function(soup):
    # Extract the "Factors Related to Cognitive Decline" section
    cognitive_section = soup.find("div", id="OutOfRange")
    if not cognitive_section:
        return {}

    # Title
    title_tag = cognitive_section.find("h1", id="ShdMrpFactors")
    title = title_tag.get_text(" ", strip=True) if title_tag else "Factors Related to Cognitive Decline"

    # Intro paragraph
    intro_p = title_tag.find_next("p") if title_tag else None
    intro = intro_p.get_text(" ", strip=True) if intro_p else ""

    # Extract all tabSummary tables
    tables = cognitive_section.find_all("table", class_="tabSummary")
    factors = []
    for tbl in tables:
        # Section title
        th = tbl.find("th")
        section_title = th.get_text(" ", strip=True) if th else ""

        # Each tabSummary table should map to a single factor object
        factor = {
            "section": section_title,
            "entries": []
        }

        # Each <td> is a factor entry
        for tr in tbl.find_all("tr", recursive=False)[1:]:
            function = ""
            small_text = ""
            immediate_text = ""
            
            td = tr.find("td", colspan="1")
            if td:
                # Get text only immediately inside <td> (not from children)
                immediate_text = "".join(t for t in td.contents if isinstance(t, str)).strip()
                # Get text from the immediate <small> tag (if present)
                small_tag = td.find("small", recursive=False)
                small_text = small_tag.get_text(" ", strip=True) if small_tag else ""

            table = tr.find("table")
            if table:
                function = table.get_text(" ", strip=True).strip()

            target_level = ""
            target_match = re.search(r"target:\s*([<≥>=]*\s*[0-9.]+\s*[^\s]+)", function)
            if target_match:
                target_level = target_match.group(1).strip()
                function = function.replace(target_match.group(1), "").strip()
                function = function.replace("target:", "").strip()

            current_level = ""
            
            # if function:
            #     m = re.search(r"([A-Za-z\s\-]+)?([0-9.]+)\s*([^\s]+)?$", function)
            #     print("Function:", m)
            #     if m:
            #         current_level = m.group(2)
            #         if m.group(3):
            #             current_level += " " + m.group(3).strip()
            #     else:
            #         current_level = function
            
            pattern = re.compile(
                r'(?i)^\s*(very\s+high|high|very\s+low|low|moderately\s+high|moderately\s+low)\s+'  # group 1: severity phrase
                r'(.+?)\s+'                                      # group 2: measurement label
                r'(\d+(?:\.\d+)?(?:\s*\S+)*?)\s*$'               # group 3: number + optional units
            )
            severity, measurement, value = "", "", ""
            m = pattern.match(function)
            if m:
                # print("Function:", m)
                severity, measurement, value = m.groups()

            img = None
            img_tag = tr.find("img", recursive=False)
            if img_tag and img_tag.has_attr("src"):
                img = img_tag["src"]

            factor["entries"].append({
                "description": immediate_text + "\n" + small_text,
                "severity": severity.strip() if severity else "",
                "measurement": measurement.strip() if measurement else "",
                "currentLevel": value.strip() if value else "",
                # "currentLevel": current_level,
                "targetLevel": target_level,
                "image": img
            })

        factors.append(factor)

    return {
        "title": title,
        "intro": intro,
        "factors": factors
    }
    
def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.replace(NBSP, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _strip_trailing_and(s: str) -> str:
    return re.sub(r"[,\s]*(?:and)?\s*$", "", s, flags=re.I)

def parse_reasoning_cell(cell: Tag):
    # Turn Reasoning cell into structured records
    text = cell.get_text("\n", strip=True).replace(NBSP, " ")
    lines = [ln for ln in (l.strip() for l in text.split("\n")) if ln]

    out = []
    current_action = None
    for ln in lines:
        if ln.endswith(":"):
            current_action = ln[:-1].strip()
            continue

        if ln.startswith(BULLET_CHARS) or ln.startswith("-") or ln.startswith("&bull;"):
            item = ln.lstrip("•\u2022-&bull; ").strip()
            item = _strip_trailing_and(item)
            m = re.match(r"(.+?)\s*\((.+?)\)\.?\s*$", item)
            if m:
                name, val = m.groups()
                out.append({"action": current_action or "", "name": _norm(name), "currentValue": _norm(val)})
            else:
                out.append({"action": current_action or "", "note": _norm(item)})
        else:
            out.append({"note": _norm(ln)})
    return out

def extract_supplements(soup: BeautifulSoup):
    root = soup.find("div", id="InterventionMeds")
    if not root:
        return None

    h3 = root.find("h3", id="ShdMrpMedsSupplements")
    if not h3:
        return None

    title = _norm(h3.get_text(" ", strip=True))

    # ---- intro paragraphs between h3 and first following table (even if nested) ----
    intro = []
    supplements_table = None

    # Walk forward through the document (across custom wrappers)
    for el in h3.next_elements:
        if isinstance(el, Tag) and el.name == "table":
            # Verify it's the supplements table by header text
            header_text = _norm(el.get_text(" ", strip=True)).lower()
            if ("new supplement" in header_text and
                "dosage details" in header_text and
                "reasoning" in header_text and
                "guidance" in header_text):
                supplements_table = el
                break
        if isinstance(el, Tag) and el.name == "p":
            if root in el.parents:
                txt = _norm(el.get_text(" ", strip=True))
                if txt:
                    intro.append(txt)

    # Fallback: search within the section for the first table with expected headers
    if not supplements_table:
        for tbl in root.find_all("table"):
            header_text = _norm(tbl.get_text(" ", strip=True)).lower()
            if ("new supplement" in header_text and
                "dosage details" in header_text and
                "reasoning" in header_text and
                "guidance" in header_text):
                supplements_table = tbl
                break

    items = []
    if supplements_table:
        rows = supplements_table.find_all("tr")
        for tr in rows[1:]:  # skip header row
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue

            # Supplement name + aka in <small>
            sup_td = tds[0]
            # main name = text before <br/><small>
            main_parts = []
            for node in sup_td.children:
                if isinstance(node, NavigableString):
                    if node.strip():
                        main_parts.append(node.strip())
                elif isinstance(node, Tag) and node.name.lower() in {"br", "small"}:
                    break
            supplement = _norm(" ".join(main_parts)) or _norm(sup_td.get_text(" ", strip=True))
            aka_tag = sup_td.find("small")
            aka = _norm(aka_tag.get_text(" ", strip=True)) if aka_tag else ""

            dosage = _norm(tds[1].get_text(" ", strip=True))
            reasoning = parse_reasoning_cell(tds[2])
            guidance = _norm(tds[3].get_text(" ", strip=True))

            items.append({
                "supplement": supplement,
                "aka": aka,
                "dosageDetails": dosage,
                "reasoning": reasoning,
                "guidance": guidance
            })

    # ---- Tips block after the table ----
    tips = None
    if supplements_table:
        # Find the first <p> after the table containing a <b> with "Tips"
        p = supplements_table.find_next(lambda tag: (
            isinstance(tag, Tag) and tag.name == "p" and tag.find("b") and
            "tips" in _norm(tag.find("b").get_text(" ", strip=True)).lower()
        ))
        if p:
            tips_title = _norm(p.find("b").get_text(" ", strip=True))
            ul = p.find("ul")
            bullets = [_norm(li.get_text(" ", strip=True)) for li in ul.find_all("li")] if ul else []
            # trailing note: other text nodes not in <b> or <ul>
            trailing_parts = []
            for node in p.contents:
                if isinstance(node, NavigableString):
                    t = _norm(str(node))
                    if t:
                        trailing_parts.append(t)
                elif isinstance(node, Tag) and node.name.lower() not in {"b", "ul"}:
                    t = _norm(node.get_text(" ", strip=True))
                    if t:
                        trailing_parts.append(t)
            trailing_text = " ".join(trailing_parts)
            if tips_title and trailing_text.startswith(tips_title):
                trailing_text = trailing_text[len(tips_title):].strip()

            tips = {
                "title": tips_title,
                "bullets": bullets,
                "note": trailing_text if trailing_text else ""
            }

    return {
        "title": title,
        "intro": [t for t in intro if t],
        "items": items,
        "tips": tips
    }

def _cell_paragraphs(td: Tag) -> list[str]:
    """
    Normalize a <td> into paragraphs:
    - Convert <br> to newlines
    - Collapse whitespace
    - Split into logical paragraphs
    """
    # duplicate so we don't mutate original
    td_copy = BeautifulSoup(str(td), "html.parser")
    for br in td_copy.find_all("br"):
        br.replace_with("\n")
    text = td_copy.get_text("\n", strip=True).replace(NBSP, " ")
    # collapse triple newlines down to single paragraph breaks
    text = re.sub(r"\n{2,}", "\n\n", text)
    # split on blank lines
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    # final whitespace collapse in each paragraph
    return [re.sub(r"\s+", " ", p) for p in paras]

def _find_following_table_with_headers(start: Tag, headers: list[str]) -> Tag | None:
    hdrs_lower = [h.lower() for h in headers]
    for el in start.next_elements:
        if isinstance(el, Tag) and el.name == "table":
            head_txt = _norm(el.get_text(" ", strip=True)).lower()
            if all(h in head_txt for h in hdrs_lower):
                return el
        # stop if we hit a new major section
        if isinstance(el, Tag) and el.name in {"h1", "h2"} and el is not start:
            break
    return None

# def extract_lifestyle(soup: BeautifulSoup) -> dict | None:
#     """
#     Produces:
#     {
#       "title": "Your Lifestyle",
#       "intro": [ ... ],
#       "image": { "src": "...", "width": 758, "height": 301 } | null,
#       "items": [
#         {
#           "area": "Stress Relief",
#           "icon": { "src": "...", "width": 70, "height": 70 } | null,
#           "task": "Find at least 30 minutes...",
#           "instructions": ["Para 1", "Para 2", ...]
#         },
#         ...
#       ]
#     }
#     """
#     h2 = soup.find("h2", id="ShdMrpLifestyle")
#     if not h2:
#         return None

#     title = _norm(h2.get_text(" ", strip=True))

#     # 1) Intro paragraphs between the H2 and the lifestyle table
#     intro: list[str] = []
#     # We’ll accumulate <p> text nodes until we find the target table
#     target_headers = ["Lifestyle Area", "Your Task", "Additional Instructions"]
#     lifestyle_table = _find_following_table_with_headers(h2, target_headers)

#     for el in h2.next_elements:
#         if el is lifestyle_table:
#             break
#         if isinstance(el, Tag) and el.name == "p":
#             # only count paragraphs before the table and within same section
#             intro.append(_norm(el.get_text(" ", strip=True)))
#         # stop if a new section starts before we found the table (safety)
#         if isinstance(el, Tag) and el.name in {"h1", "h2"} and el is not h2:
#             break

#     # Deduplicate intro and drop empties
#     intro = [t for i, t in enumerate(intro) if t and (i == 0 or t != intro[i-1])]

#     # 2) First image between H2 and the table (centered lifestyle image)
#     image = None
#     if lifestyle_table:
#         for el in h2.next_elements:
#             if el is lifestyle_table:
#                 break
#             if isinstance(el, Tag) and el.name == "img":
#                 src = el.get("src") or ""
#                 w = el.get("width")
#                 h = el.get("height")
#                 image = {
#                     "src": src,
#                     "width": int(w) if (w and str(w).isdigit()) else None,
#                     "height": int(h) if (h and str(h).isdigit()) else None,
#                 }
#                 break

#     # 3) Parse the lifestyle table rows
#     items = []
#     if lifestyle_table:
#         rows = lifestyle_table.find_all("tr")
#         for tr in rows[1:]:  # skip header
#             tds = tr.find_all("td")
#             if len(tds) < 3:
#                 continue

#             # Area cell: bold title before <br>, then an <img> icon
#             area_td = tds[0]
#             # title: prefer bold text before <br>
#             area_title = ""
#             b = area_td.find("b")
#             if b:
#                 # text up to first <br>
#                 parts = []
#                 for node in b.children:
#                     if isinstance(node, NavigableString):
#                         parts.append(str(node))
#                     elif isinstance(node, Tag) and node.name == "br":
#                         break
#                 area_title = _norm("".join(parts))
#             if not area_title:
#                 area_title = _norm(area_td.get_text(" ", strip=True))

#             # icon
#             icon = None
#             img = area_td.find("img")
#             if img:
#                 iw = img.get("width")
#                 ih = img.get("height")
#                 icon = {
#                     "src": img.get("src") or "",
#                     "width": int(iw) if (iw and str(iw).isdigit()) else None,
#                     "height": int(ih) if (ih and str(ih).isdigit()) else None,
#                 }

#             # Task cell (may be &nbsp;)
#             task_td = tds[1]
#             task_text = _norm(task_td.get_text(" ", strip=True))
#             if task_text == "&nbsp;" or task_text == " ":
#                 task_text = ""

#             # Additional instructions as paragraphs
#             instr_td = tds[2]
#             instructions = _cell_paragraphs(instr_td)

#             items.append({
#                 "area": area_title,
#                 "icon": icon,
#                 "task": task_text,
#                 "instructions": instructions
#             })

#     return {
#         "title": title,
#         "intro": intro,
#         "image": image,
#         "items": items
#     }

def main(path: str, output: str):
    # Read as raw bytes so BeautifulSoup can detect encoding
    path = "Report_Participant_1-00_JANEADOE_2024-11-02.html"
    with open(path, 'rb') as f:
        raw = f.read()

    # Let BeautifulSoup handle the decoding
    soup = BeautifulSoup(raw, 'html.parser')

    report = {
        "preface": extract_preface(soup),
        "healthReport": extract_health_report(soup),
        "actionPlan": extract_action_plan(soup),
        "lifestyle": extract_lifestyle(soup),
        "nutrition": extract_nutrition(soup),
        "currentMedication": extract_current_medication(soup),
        "cognitiveFunction": extract_cognitive_function(soup)
        
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
