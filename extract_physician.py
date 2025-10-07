import time
import os
import json
import re
from bs4 import BeautifulSoup
from utils import load_biomedical_terms, extract_risk_tokens
import re

def extract_intro(soup: BeautifulSoup) -> dict:
    # Extract the title
    title_tags = soup.select("#topmatter .head")
    titles = [tag.get_text(strip=True) for tag in title_tags]

    # Extract participant table data
    participant_table = soup.select_one("#Participant table")
    participant_data = {}
    if participant_table:
        for row in participant_table.find_all("tr"):
            label = row.find("span", class_="label")
            value = row.find("span", class_="value")
            if label and value:
                participant_data[label.get_text(strip=True).strip(":")] = value.get_text(strip=True)

    # Extract practice table data
    practice_table = soup.select_one("#Practice table")
    practice_data = {}
    if practice_table:
        for row in practice_table.find_all("tr"):
            label = row.find("span", class_="label")
            value = row.find("span", class_="value")
            b_elem = value.find("b")
            bold_text = None
            sibling_text = None
            if b_elem:
                # Extract bold text and its sibling, then remove from value text
                bold_text = b_elem.get_text(strip=True)
                sibling_text = b_elem.next_sibling.strip() if b_elem.next_sibling else ""

                # Remove bold text and sibling from value text
                full_value = value.get_text(strip=True)
                cleaned_value = full_value.replace(bold_text, "", 1).replace(sibling_text, "", 1).strip()
                value.string = cleaned_value
                
            if label and value:
                practice_data[label.get_text(strip=True).strip(":")] = value.get_text(strip=True)
            if bold_text:
                practice_data[bold_text] = sibling_text
                
    # Overview table under “YourStatus”
    status_tbl = soup.select_one("#SummaryDigest table")
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

        # key = "".join(ch for ch in h if ch.isalnum())
        key = h
        overview[key] = {
            "value": base,
            "annotations": ann
        }

    return {
        "titles": titles,
        "participant": participant_data,
        "practice": practice_data,
        "overview": overview
    }
    
def extract_cognitive_assessment(soup: BeautifulSoup) -> dict:
    # Find the main cognitive assessment table by searching for the heading text
    # heading = "Complete the following elements of Cognitive Assessment and Care Plan Services"
    # main_b = soup.find("b", string=lambda s: s and heading in s)
    
    
    main_b = soup.select_one("#SummaryDigest").find_next_sibling()
    if not main_b:
        return {}

    # The table is the next sibling after the heading
    main_table = main_b.find_next("table")
    if not main_table:
        return {}

    results = {}

    # Find all innermost <td> elements containing a <b><u> heading
    for td in main_table.select("td td"):
        b_u = td.find("b")
        if not b_u or not b_u.find("u"):
            continue
        heading_text = b_u.get_text(strip=True).replace("\n", " ").replace("\r", " ")
        # Remove trailing <br /> from heading
        heading_text = heading_text.rstrip("<br />").strip()

        # Find the <small> after the heading
        small = td.find("small")
        if not small:
            continue
        items = []
        # Checkbox case: <img> followed by text
        for img in small.find_all("img"):
            next_text = img.next_sibling
            if next_text and isinstance(next_text, str):
                txt = next_text.strip()
            if txt:
                items.append({"text": txt, "checkbox": True})

        # Score and plain text case: handle all text nodes (excluding <img>)
        small_text = small.get_text(separator="\n")
        lines = [l.strip() for l in small_text.split("•") if l.strip()]
        for line in lines:
            # Try to match "Label: <b>value</b>" pattern
            if ":" in line:
                parts = line.split(":")
                label = parts[0].split(" ")[-1].strip()
                rest = ":".join(parts[1:]).strip()
                num_match = re.search(r"\b(\d+)\b", rest)
                value = int(num_match.group(1)) if num_match else None
                cleaned = line.strip()
                if num_match:
                    cleaned = cleaned.replace(str(value), "").strip()
                    # cleaned = cleaned.replace(label, "")
                    cleaned = cleaned.replace(":", "").strip()
                    items.append({"text": cleaned, "value": value, "checkbox": False})
                elif line:
                    items.append({"text": line.split("\n")[-1].strip(), "checkbox": False})

        results[heading_text] = items

    return results


def extract_code_and_question(td):
    VALID_CODES = set("STOPBANG")
    """
    Return (code, question_text).
    Tries:
      1) find a single-letter <b> or <strong> tag that matches STOPBANG
      2) fallback to a tolerant regex on the cell text
    """
    # 1) DOM-first: look for a bold/strong tag that contains exactly one letter in STOPBANG
    for tag_name in ("b", "strong"):
        tag = td.find(tag_name)
        if tag:
            letter = tag.get_text(strip=True)
            if len(letter) == 1 and letter.upper() in VALID_CODES:
                code = letter.upper()
                # collect everything after that tag as the question
                parts = []
                for sib in tag.next_siblings:
                    # next_siblings can be Tag, NavigableString, etc.
                    if hasattr(sib, "get_text"):
                        parts.append(sib.get_text(" ", strip=True))
                    else:
                        parts.append(str(sib).strip())
                question = " ".join(p for p in parts if p).strip()
                # remove a leading colon/other punctuation if present
                question = re.sub(r'^[\s:：\-\)\.]+', '', question).strip()
                # fallback: if nothing found after the tag, remove the tag text from full text
                if not question:
                    full = td.get_text(" ", strip=True)
                    question = re.sub(r'^\s*' + re.escape(letter) + r'\s*[:：\-\)\.]*\s*', '', full).strip()
                return code, question

    # 2) Fallback to tolerant regex on the flattened text
    text = td.get_text(" ", strip=True)
    # allow leading whitespace, a single letter, optional separator (colon, unicode colon, dash, dot, right-paren)
    m = re.match(r'^\s*([A-Za-z])\s*[:：\-\)\.]?\s*(.*)', text, flags=re.DOTALL)
    if m and m.group(1).upper() in VALID_CODES:
        return m.group(1).upper(), m.group(2).strip()
    # 3) no code found
    return None, text

def extract_stopbang(soup: BeautifulSoup) -> dict:
    result = {}
    root = soup.select_one("#StopbangTable")
    title = root.find("h3", id="AhdStopbang")
    if title:
        result["title"] = title.get_text(strip=True)

    # 2. Preface (definition + risk rules)
    preface_div = title.find_next("div")
    preface_parts = {}
    if preface_div:
        paragraphs = preface_div.find_all("p", recursive=False)

        if len(paragraphs) >= 1:
            preface_parts["definition"] = paragraphs[0].get_text(" ", strip=True)

        if len(paragraphs) >= 2:
            preface_parts["risk_intro"] = paragraphs[1].get_text(" ", strip=True)

        # Risk rules (inside <ul>)
        risk_ul = preface_div.find("ul")
        if risk_ul:
            risk_rules = {}
            for li in risk_ul.find_all("li", recursive=False):
                text = li.get_text(" ", strip=True)
                # Extract the part before ":" as the property name
                if ":" in text:
                    prop, rest = text.split(":", 1)
                    key = prop.strip()
                    risk_rules[key] = rest.strip()
                else:
                    risk_rules[text.strip().lower().replace(" ", "_")] = text
            preface_parts["risk_rules"] = risk_rules

    result["preface"] = preface_parts

    # 3. Table parsing
    table = root.find("table")
    yes_count = 0
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    result["headers"] = headers

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) == 3:
            code, question = extract_code_and_question(cells[0])
            answer = cells[1].get_text(" ", strip=True)
            explanation = cells[2].get_text(" ", strip=True)
            
            if answer.lower() == "yes":
                yes_count += 1
            
            row = {
                "code": code,
                "question": question,
                "answer": answer,
                "explanation": explanation,
            }
            rows.append(row)

    result["table"] = rows

    # 4. Postface parsing (risk + score)
    postface_div = table.find_next("div")
    if postface_div:
        postface_text = postface_div.get_text(" ", strip=True)
        result["postface"] = postface_text

        # Extract score if present (e.g. "7 Yes answers")
        score_match = re.search(r"(\d+)\s+Yes answers", postface_text)
        if score_match:
            result["score"] = int(score_match.group(1))
            
        if "high" in postface_text.lower():
            result["risk_level"] = "High"
        elif "intermediate" in postface_text.lower():
            result["risk_level"] = "Intermediate"
        elif "low" in postface_text.lower():
            result["risk_level"] = "Low"
            
    result["calculated_score"] = yes_count
    return result

def extract_acb(soup: BeautifulSoup) -> dict:
    # --- Extract Preface ---
    root = soup.select_one("#ACBTable")
    title = root.find("h3", id="AhdACB")
    # --- Extract all <div> blocks ---
    div = root.find_next("div")
    paras = div.find_all("p", recursive=False) if div else []

    # Root preface: everything before the criteria block
    root_preface_parts = []
    criteria_block = div
    for d in paras:
        text = d.get_text(" ", strip=True)
        if text:
            root_preface_parts.append(text)
    root_preface = " ".join(root_preface_parts)

    # Criteria preface: only the last div inside criteria before <ol>
    criteria_preface_parts = []
    if criteria_block:
        for child in criteria_block.children:
            if getattr(child, "name", None) == "ol":
                break
            if child.get_text(strip=True):
                criteria_preface_parts = [child.get_text(" ", strip=True)]
    criteria_preface = " ".join(criteria_preface_parts)

    # Extract <li> items from criteria
    criteria_items = []
    if criteria_block:
        for li in criteria_block.find_all("li"):
            score = li.get("value")
            desc = li.get_text(" ", strip=True)
            if score:
                criteria_items.append({
                    "score": int(score),
                    "description": desc
                })

    table = root.find("table")
    # --- Extract Postface ---
    postface_block = table.find_next("div") if table else None
    postface_might_list = postface_block.find_next("ul") if postface_block else None
    notes_list = postface_might_list.find_next("ul") if postface_might_list else None
    postface_text_raw = postface_block.get_text(" ", strip=True) if postface_block else ""

    # Split into "mights" and main text
    mights = re.findall(r"(Might .*?\?)", postface_text_raw)
    mights = [li.get_text(" ", strip=True) for li in postface_might_list.find_all("li")] if postface_might_list else []
    main_postface = re.sub(r"(Might .*?\?)", "", postface_text_raw).strip()
    notes = [li.get_text(" ", strip=True) for li in notes_list.find_all("li")] if notes_list else []

    criteria = {
        "preface": criteria_preface,
        "items": criteria_items,
    }

    # --- Extract Table ---
    headers = [th.get_text(strip=True) for th in table.find_all("th") if th.get_text(strip=True).lower() != "dosage"]
    
    table_obj = {
        "headers": headers
    }
    table_data = []
    if table:
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cols = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cols) == 4:
                medication, dosage, score, alternatives = cols
                # Split alternatives, clean "or"
                alt_list = [alt.strip() for alt in re.split(r",|\bor\b", alternatives)]
                alt_list = [a for a in alt_list if a]
                table_data.append({
                    "medication": medication,
                    "dosage": dosage,
                    "score": int(score),
                    "alternatives": alt_list
                })
                
    table_obj["data"] = table_data

    # --- Extract Totals & Notes ---
    totals = {}
    if postface_block:
        text = postface_block.get_text(" ", strip=True)
        total_score_match = re.search(r"total ACB score is\s+(\d+)", text, re.I)
        definite_count_match = re.search(r"of which there are currently\s+(\d+)", text, re.I)
        mmse_effect_match = re.search(r"may be lowering an MMSE score by\s+(\d+)", text, re.I)

        totals = {
            "total_acb_score": int(total_score_match.group(1)) if total_score_match else None,
            "definite_anticholinergics": int(definite_count_match.group(1)) if definite_count_match else None,
            "mmse_effect": int(mmse_effect_match.group(1)) if mmse_effect_match else None,
        }

    # --- Final JSON-like structure ---
    acb_data = {
        "title": title.get_text(strip=True) if title else "",
        "root_preface": root_preface,
        "criteria": criteria,
        "medications": table_obj,
        "totals": totals,
        "postface": {
            "text": main_postface,
            "mights": mights,
            "notes": notes
        }
    }
    return acb_data

def extract_leqembi(soup: BeautifulSoup) -> dict:
    result = {}

    # --- Extract title ---
    root = soup.select_one("#Aduhelm")
    h3 = root.select_one("#AhdAduhelm")
    if h3:
        result["heading"] = h3.get_text(strip=True)

    # # --- Preface ---
    # preface_divs = root.find_all("p", recursive=False)
    # if preface_divs:
    #     prefaces = [p.get_text(" ", strip=True) for p in preface_divs if p.get_text(strip=True)]
    #     if len(prefaces) > 1:
    #         result["preface"] = " ".join(prefaces[:-1])
    #         conclusion = prefaces[-1].lstrip("Conclusion:").strip()
    #         result["conclusion"] = conclusion
    #     else:
    #         result["preface"] = prefaces[0]
    
    # Preface (first <p> before any tables)
    legend_table = None
    paragraphs = []
    preface_divs = root.find_all("p", recursive=False)
    for p in preface_divs[0:-1]:  # all except last
        table = p.find("table")
        if table and not legend_table:
            legend_table = table
            if legend_table:
                # Remove the table from the paragraph text
                text = p.get_text(" ", strip=True)
                table_text = legend_table.get_text(" ", strip=True)
                cleaned_text = text.replace(table_text, "").strip()
                if cleaned_text:
                    result["legend_preface"] = cleaned_text
            continue
        text = p.get_text(" ", strip=True)
        if text:
            paragraphs.append(text)
    result["preface"] = paragraphs
    conclusion = preface_divs[-1].get_text(" ", strip=True).lstrip("Conclusion:").strip()
    result["conclusion"] = conclusion
            
    # Legend (first table with class="no_border")
    legend = []
    if legend_table:
        for td in legend_table.find_all("td"):
            text = td.get_text(" ", strip=True)
            if text:  # filter empty
                legend.append(text)
    result["legend"] = legend

    # --- Criteria Table ---
    criteria_tables = root.find_all("table")
    criteria_table = criteria_tables[1] if len(criteria_tables) > 1 else None
    headers = [th.get_text(strip=True) for th in criteria_table.find_all("th")]
    result["headers"] = headers

    criteria = []
    if criteria_table:
        rows = criteria_table.find_all("tr")[1:]  # skip header
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                crit_text = cols[0].get_text(" ", strip=True)
                status = cols[1].get_text(" ", strip=True)
                reasoning = cols[2].decode_contents()

                # normalize reasoning list if nested table
                nested_items = cols[2].find_all("td", class_="no_border")
                if nested_items:
                    reasoning = [td.decode_contents() for td in nested_items if td.get_text(strip=True).lstrip("• ").strip()]

                criteria.append({
                    "criterion": crit_text,
                    "status": status,
                    "reasoning": reasoning
                })
    result["criteria"] = criteria

    # --- Postface + Conclusion ---
    postface_parts = []
    conclusion_texts = []
    conclusion = soup.find("b", string=re.compile("Conclusion", re.I))
    if conclusion:
        parent = conclusion.find_parent("p")
        if parent:
            conclusion_texts.append(parent.get_text(" ", strip=True))
            # get sibling paragraphs
            for sib in parent.find_all_next("p"):
                txt = sib.get_text(" ", strip=True)
                if txt:
                    conclusion_texts.append(txt)

    if conclusion_texts:
        # detect eligibility
        joined_conclusion = " ".join(conclusion_texts).lower()
        if "does not meet" in joined_conclusion or "ineligible" in joined_conclusion or "not eligible" in joined_conclusion:
            result["eligibility"] = "Ineligible"
        elif "meets" in joined_conclusion or "eligible" in joined_conclusion:
            result["eligibility"] = "Eligible"
        else:
            result["eligibility"] = "Unknown"

        # result["postface"] = conclusion_texts

    return result

def extract_fall_risk(soup: BeautifulSoup) -> dict:
    result = {}
    heading = soup.select_one("#ShdMrtdFallRisk")
    result["heading"] = heading.get_text(" ", strip=True)
    
    div = heading.find_next_sibling("div")
    if div:
        paragraphs = [p.get_text(" ", strip=True) for p in div.find_all("p", recursive=False)]
        result["preface"] = paragraphs

        # headers = [th.get_text(" ", strip=True) for th in heading.find_all_next("th")] if heading else []
        headers = []
        columnTypes = []
        for th in div.find_all("th"):
            text = th.get_text(strip=True)
            # Remove any pattern like (- ... =) or ( ... =) from the header text
            cleaned_text = re.sub(r'\(\s*[^()]*=\s*[^()]*\)', '', text).strip()
            if cleaned_text.lower() != "dosage":
                headers.append(cleaned_text)
                if "text-align:center" in th.decode_contents().lower():
                    columnTypes.append("numeric")
                else:
                    columnTypes.append("alpha")
                    
        result["columnTypes"] = columnTypes
        result["headers"] = headers
        
        medications = []
        total_score = 0
        for tr in div.find_all("tr")[1:] if div else []:
            medication = {}
            tds = tr.find_all("td")
            if len(tds) >= 3:
                medication["name"] = tds[0].get_text(" ", strip=True)
                medication["dosage"] = tds[1].get_text(" ", strip=True)
                score = tds[2].get_text(" ", strip=True)
                medication["score"] = score
                total_score += int(score or 0)

            medications.append(medication)

        result["medications"] = medications
        result["totalScore"] = total_score
        
    return result

def extract_additional_diagnostics(soup: BeautifulSoup) -> dict:
    root = soup.select_one("#AdditionalDiagnostics")
    heading = root.select_one("#ShdMrtdTestRequests")
    table = root.find("table")
    result = {
        "heading": heading.get_text(strip=True) if heading else "",
        "segments": {}
    }
    
    if not table:
        return result
    
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    result["headers"] = headers
    
    current_segment = None
    segments = {}
    
    for tr in table.find_all("tr"):
        # Check if this is a separator row
        sep_td = tr.find("td", class_="SepFindings")
        if sep_td:
            # This is a segment header
            segment_name = sep_td.get_text(strip=True)
            current_segment = segment_name
            segments[current_segment] = []
            continue
        
        # Skip header row
        if tr.find("th"):
            continue
            
        # Regular data row
        tds = tr.find_all("td")
        if len(tds) >= 2 and current_segment:
            test_name = tds[0].get_text(strip=True)
            explanation = tds[1].get_text(strip=True)
            terms = load_biomedical_terms(os.path.join(os.path.dirname(__file__), "biomedical_terms.csv"))
            findings = extract_risk_tokens(explanation, terms)
            tokens = [f for f in findings if f.get("name") != None]  # filter out empty findings
            
            segments[current_segment].append({
                "test": test_name,
                "explanation": explanation,
                "tokens": tokens
            })
    
    result["segments"] = segments
    return result

def extract_cognitive_factors(soup: BeautifulSoup) -> dict:
    categoty_map = {
        "Green": "Optimal",
        "Yellow": "Caution",
        "LightSalmon": "At Risk",
        "LightGray": "Unknown"
    }
    # Locate the "Analysis of Cognitive Factors" header
    analysis_section = soup.find("h2", string="Analysis of Cognitive Factors")
    
    # If the section is not found, return an empty structure
    if not analysis_section:
        return {"title": "Analysis of Cognitive Factors", "healthStatusSections": []}
    
    # Find the table that follows the header
    analysis_table = analysis_section.find_next("table")
    
    # List to store each cognitive factor section
    status_sections = []
    
    # Categories to loop through: Green, Yellow, Red, Gray
    categories = ["Green", "Yellow", "LightSalmon", "LightGray"]
    
    for category in categories:
        # Look for the row with the specific class that identifies the category
        category_row = analysis_table.find("td", class_="tdBackground" + category + "Left")
        
        if category_row:
            section = {
                "title": categoty_map.get(category, "Unknown"),
                "count": 0,  # Placeholder count, adjust if needed
                "description": category_row.get_text(strip=True).split(":", 1)[-1].strip(),
                "factors": []
            }
            
            # Find the table with the factors under each category
            factors_table = category_row.find_next("table")
            if factors_table:
                # Extract the factors from the table rows
                factors = factors_table.find_all("tr", class_="no_border")
                for factor in factors:
                    factor_text = factor.get_text(strip=True)
                    if factor_text:
                        # Split factors based on the bullet character (•) and clean up
                        split_factors = factor_text.split("•")
                        for factor_item in split_factors:
                            factor_cleaned = factor_item.strip()
                            if factor_cleaned:  # Only add non-empty factors
                                section["factors"].append(factor_cleaned)
                                section["count"] = len(section["factors"])
            
            status_sections.append(section)
    
    return {
        "title": "Analysis of Cognitive Factors",
        "healthStatusSections": status_sections
    }

def parse_recommendation_sentence(sentence: str) -> dict:
    # Pattern 1: "[Issue] is [modifier] target, at [value]"
    pattern1 = r'^(.+?)\s+is\s+(?:far\s+)?(?:above|below)\s+target,\s+at\s+(.+?)[.\s]*$'
    
    # Pattern 2: "[Issue] calculated at [value] indicates..."
    pattern2 = r'^(.+?)\s+calculated\s+at\s+([\d.]+)\s+'
    
    # Try pattern 1 first
    match = re.match(pattern1, sentence, re.IGNORECASE)
    
    if match:
        issue = match.group(1).strip()
        value = match.group(2).strip()
        
        return {
            "issue": issue,
            "value": value,
            "sentence": sentence
        }
    
    # Try pattern 2
    match = re.match(pattern2, sentence, re.IGNORECASE)
    
    if match:
        issue = match.group(1).strip()
        value = match.group(2).strip()
        
        return {
            "issue": issue,
            "value": value,
            "sentence": sentence
        }
    
    # If no pattern matches, just return the sentence
    return {
        "sentence": sentence
    }

def extract_medical_issues(soup: BeautifulSoup) -> dict:
    # Find the "Additional Medical Issues" header
    additional_issues_section = soup.find("h3", string="Additional Medical Issues")
    
    if not additional_issues_section:
        return {"title": "Additional Medical Issues", "issues": []}
    
    # Fin the intro text that follows the header
    intro_paragraph = additional_issues_section.find_next("p")
    
    # Find the table that follows the header
    issues_table = additional_issues_section.find_next("table")
    
    # List to store all medical issues
    issues = []
    
    # Extract the rows of the table that contain the medical issues
    rows = issues_table.find_all("tr", class_=["odd", "even"])
    
    # Iterate over the rows to extract information
    for row in rows:
        issue_data = {}
        # Find the issue name (e.g., "Plaques and Tangles")
        issue_name = row.find("b")
        if issue_name:
            issue_data["issueName"] = issue_name.get_text(strip=True)
        
        # Find the table under each issue for the warnings and recommendations
        issue_table = row.find("table", class_="no_border")
        
        if issue_table:
            warnings = []
            recommendations_raw = []
            
            # Extract all rows in the issue table
            issue_rows = issue_table.find_all("tr", class_="no_border")
            for issue_row in issue_rows:
                # Find the warning (e.g., "AD-Detect™ p-tau181 is far above target")
                warning_text = issue_row.find("td", width="65%")
                if warning_text:
                    warnings.append(warning_text.get_text(strip=True))
                
                # Find the recommendation (e.g., "Further evaluation is recommended")
                recommendation_text = issue_row.find("td", width="32%")
                if recommendation_text:
                    recommendations_raw.append(recommendation_text.get_text(strip=True))

            # NEW: structure recommendations
            structured_recs = [parse_recommendation_sentence(r) for r in recommendations_raw]

            issue_data["warnings"] = warnings
            issue_data["recommendations"] = structured_recs

            # Adding the extracted data for the issue
            issue_data["warnings"] = warnings
            issue_data["recommendations"] = structured_recs
        
        issues.append(issue_data)
    
    return {
        "title": "Additional Medical Issues",
        "issues": issues,
        "intro": intro_paragraph.get_text(strip=True) if intro_paragraph else ""
    }



def extract_comorbidities(soup: BeautifulSoup) -> dict:
    # Locate the "Current Comorbidities" header
    comorbidities_section = soup.find("h3", string="Current Comorbidities")
    
    # If the section is not found, return an empty structure
    if not comorbidities_section:
        return {"title": "Current Comorbidities", "comorbidities": []}
    
    # Find the table that follows the header
    comorbidities_table = comorbidities_section.find_next("table")
    
    # List to store the extracted comorbidities
    comorbidities = []
    
    # Extract the rows of the table (skipping the header row)
    rows = comorbidities_table.find_all("tr")[1:]  # Skipping header row
    
    for row in rows:
        comorbidity_data = {}
        
        # Find the comorbidity name (first column)
        comorbidity_name = row.find_all("td")[0].get_text(strip=True)
        if comorbidity_name:
            comorbidity_data["comorbidity"] = comorbidity_name
        
        # Find the diagnosis date (second column)
        diagnosis_date = row.find_all("td")[1].get_text(strip=True)
        if diagnosis_date:
            comorbidity_data["dateDiagnosed"] = diagnosis_date
        
        # Add the comorbidity data to the list
        if comorbidity_data:
            comorbidities.append(comorbidity_data)
    
    return {
        "title": "Current Comorbidities",
        "comorbidities": comorbidities
    }

def extract_reported_and_inferred_comorbidities(soup: BeautifulSoup) -> dict:
    # Locate the "Reported and Inferred Comorbidities" header
    comorbidities_section = soup.find("h3", string="Reported and Inferred Comorbidities")
    
    # If the section is not found, return an empty structure
    if not comorbidities_section:
        return {"title": "Reported and Inferred Comorbidities", "data": []}
    
    # Extract the paragraph for the V28 implementation plan
    paragraph = comorbidities_section.find_next("p")
    paragraph_text = paragraph.get_text(strip=True) if paragraph else ""
    
    # Find the table that follows the header for V28 implementation plan
    comorbidities_table = paragraph.find_next("table")
    
    # List to store the year-wise data for V24 and V28 percentages
    v24_v28_data = []
    
    # Extract the rows of the table (skipping the header row)
    rows = comorbidities_table.find_all("tr")[1:]  # Skipping header row
    
    for row in rows:
        comorbidity_data = {}
        
        # Find the year (first column)
        year = row.find_all("td")[0].get_text(strip=True)
        if year:
            comorbidity_data["year"] = year
        
        # Find the V24 value (second column)
        v24_value = row.find_all("td")[1].get_text(strip=True)
        if v24_value:
            comorbidity_data["V24"] = v24_value
        
        # Find the V28 value (third column)
        v28_value = row.find_all("td")[2].get_text(strip=True)
        if v28_value:
            comorbidity_data["V28"] = v28_value
        
        # Add the extracted data to the list
        if comorbidity_data:
            v24_v28_data.append(comorbidity_data)

    
    # Extract the paragraph for Reported Comorbidities
    reported_paragraph = comorbidities_table.find_next("p")
    reported_paragraph_text = reported_paragraph.get_text(strip=True) if reported_paragraph else ""
    
    # Find the table with the reported comorbidities
    reported_comorbidities_table = reported_paragraph.find_next("table")
    
    # List to store reported comorbidities data
    reported_comorbidities_data = []
    
    # Extract the rows of the table (skipping the header row)
    reported_rows = reported_comorbidities_table.find_all("tr")[1:]  # Skipping header row
    
    for row in reported_rows:
        comorbidity_data = {}
        
        # Check if there are enough columns in the row
        columns = row.find_all("td")
        
        if len(columns) >= 5:
            # Extract HCC V24 value (first column)
            hcc_v24 = columns[0].get_text(strip=True)
            if hcc_v24:
                comorbidity_data["HCC V24"] = hcc_v24
            
            # Extract HCC V28 value (second column)
            hcc_v28 = columns[1].get_text(strip=True)
            if hcc_v28:
                comorbidity_data["HCC V28"] = hcc_v28
            
            # Extract ICD-10 Code (third column)
            icd_code = columns[2].get_text(strip=True)
            if icd_code:
                comorbidity_data["ICD-10 Code"] = icd_code
            
            # Extract Possible Comorbidity (fourth column)
            possible_comorbidity = columns[3].get_text(strip=True)
            if possible_comorbidity:
                comorbidity_data["Possible Comorbidity"] = possible_comorbidity
            
            # Extract Explanation (fifth column)
            explanation = columns[4].get_text(strip=True)
            if explanation:
                comorbidity_data["Explanation"] = explanation
        
            # Add the extracted data to the list
            if comorbidity_data:
                reported_comorbidities_data.append(comorbidity_data)

    
    # Extract the next paragraph after the reported comorbidities table
    inferred_paragraph = reported_comorbidities_table.find_next("p")
    inferred_paragraph_text = inferred_paragraph.get_text(strip=True) if inferred_paragraph else ""
    
    # Find the table with the inferred comorbidities
    inferred_comorbidities_table = inferred_paragraph.find_next("table")
    
    # List to store inferred comorbidities data
    inferred_comorbidities_data = []
    
    # Extract the rows of the table (skipping the header row)
    inferred_rows = inferred_comorbidities_table.find_all("tr")[1:]  # Skipping header row
    
    for row in inferred_rows:
        comorbidity_data = {}
        
        # Check if there are enough columns in the row
        columns = row.find_all("td")
        
        if len(columns) >= 5:
            # Extract HCC V24 value (first column)
            hcc_v24 = columns[0].get_text(strip=True)
            if hcc_v24:
                comorbidity_data["HCC V24"] = hcc_v24
            
            # Extract HCC V28 value (second column)
            hcc_v28 = columns[1].get_text(strip=True)
            if hcc_v28:
                comorbidity_data["HCC V28"] = hcc_v28
            
            # Extract ICD-10 Code (third column)
            icd_code = columns[2].get_text(strip=True)
            if icd_code:
                comorbidity_data["ICD-10 Code"] = icd_code
            
            # Extract Possible Comorbidity (fourth column)
            possible_comorbidity = columns[3].get_text(strip=True)
            if possible_comorbidity:
                comorbidity_data["Possible Comorbidity"] = possible_comorbidity
            
            # Extract Explanation (fifth column)
            explanation = columns[4].get_text(strip=True)
            if explanation:
                comorbidity_data["Explanation"] = explanation
        
            # Add the extracted data to the list
            if comorbidity_data:
                inferred_comorbidities_data.append(comorbidity_data)

    
    return {
        "title": "Reported and Inferred Comorbidities",
        "v28_implementation_plan": {
            "paragraph": paragraph_text,
            "v24_v28_data": v24_v28_data
        },
        "reported_comorbidities": {
            "paragraph": reported_paragraph_text,
            "reported_comorbidities_data": reported_comorbidities_data
        },
        "inferred_comorbidities": {
            "paragraph": inferred_paragraph_text,
            "inferred_comorbidities_data": inferred_comorbidities_data
        }
    }

def extract_acb_data(soup: BeautifulSoup) -> dict:
    # Find the "Anticholinergic Cognitive Burden (ACB)" header
    acb_section = soup.find("h3", id="AhdACB")
    
    if not acb_section:
        return {}  # Return empty dictionary if no ACB section found
    
    # Find the table that follows the header
    acb_table = acb_section.find_next("table")
    
    acb_data = {}
    
    # Extract the rows of the table
    rows = acb_table.find_all("tr")[1:]  # Skip the header row
    
    for row in rows:
        cells = row.find_all("td")
        
        if len(cells) >= 4:
            medication_name = cells[0].get_text(strip=True)
            dosage = cells[1].get_text(strip=True)
            acb_score = cells[2].get_text(strip=True)
            alternatives = cells[3].get_text(strip=True)
            
            # Store all the data in the dictionary
            acb_data[medication_name] = {
                "dosage": dosage,
                "acb_score": int(acb_score) if acb_score.isdigit() else None,
                "alternatives": alternatives
            }
    
    return acb_data  # Return a dictionary mapping medication name to its details


def extract_medications_fall_risk(soup: BeautifulSoup) -> dict:
    fall_risk_section = soup.find("h4", id="ShdMrtdFallRisk")
    fall_risk_data = {}

    if fall_risk_section:
        fall_risk_table = fall_risk_section.find_next("table")
        for row in fall_risk_table.find_all("tr")[1:]:  # Skip the header row
            cells = row.find_all("td")
            if len(cells) >= 3:
                medication_name = cells[0].get_text(strip=True)
                fall_risk_score = cells[2].get_text(strip=True)
                fall_risk_data[medication_name] = int(fall_risk_score)

    return fall_risk_data

def extract_medications(soup: BeautifulSoup) -> dict:
    # Find the "Current Medications" header
    current_meds_section = soup.find("h3", id="ShdMrtdCurrentMedsAndDdis")
    
    if not current_meds_section:
        return {"title": "Current Medications", "medications": []}
    
    # Find the table that follows the header
    meds_table = current_meds_section.find_next("table")
    
    # List to store all medications
    medications = []
    
    # Extract the rows of the table
    rows = meds_table.find_all("tr", class_=["odd", "even"])
    
    # Iterate over the rows to extract medication data
    for row in rows:
        medication_data = {}
        cells = row.find_all("td")
        
        if len(cells) >= 4:
            medication_data["medication"] = cells[0].get_text(strip=True)
            medication_data["dosage"] = cells[1].get_text(strip=True)
            medication_data["class_indication"] = cells[2].get_text(strip=True)
            medication_data["date_started"] = cells[3].get_text(strip=True)
        
        medications.append(medication_data)
    
    fall_risk_data = extract_medications_fall_risk(soup)
    acb_medications = extract_acb_data(soup)
    
    # Add the risks data (fall_risk_score and acb_score) to each medication
    for med in medications:
        med_name = med["medication"]
        
        # Add fall risk score if available (using substring match)
        for fall_med_name, fall_score in fall_risk_data.items():
            if fall_med_name.lower() in med_name.lower():  # Perform case-insensitive substring match
                if "risks" not in med:
                    med["risks"] = {}
                med["risks"]["fall_risk_score"] = fall_score
                break  # Once a match is found, no need to check further
        
        # Add ACB score if available (handle partial match for medication names)
        for acb_med_name, acb_data in acb_medications.items():
            if acb_med_name.lower() in med_name.lower():  # Perform case-insensitive substring match
                if "risks" not in med:
                    med["risks"] = {}
                med["risks"]["acb_score"] = acb_data["acb_score"]
                break  # Once a match is found, no need to check further
    
    
    return {
        "currentMedicationstitle": current_meds_section.get_text(strip=True),
        "medications": medications
    }
    
def extract_immune_score(soup: BeautifulSoup) -> dict:
    # Locate the "Immune Score" header
    immune_section = soup.select_one("#ImmuneScale")
    
    # If the section is not found, return an empty structure
    if not immune_section:
        return {"title": "Immune Score", "score": None, "interpretation": ""}
    
    # Find the paragraph that follows the header
    heading_div = immune_section.select_one("#AhdImmuneScale")
    heading = heading_div.get_text(strip=True) if heading_div else ""
    preface_section = immune_section.select_one("#ScoreExplanation")
    rows = preface_section.find_all("td")
    preface = rows[0].get_text(strip=True) if len(rows) > 0 else ""
    total_score = rows[1].get_text(strip=True) if len(rows) > 1 else None
    
    disclaimer = immune_section.select_one("#Disclaimer1")
    disclaimer_text = disclaimer.get_text(strip=True) if disclaimer else ""
    high_values = []
    entries = []
    
    table = disclaimer.find_next("table") if disclaimer else None
    headers = [th.get_text(strip=True) for th in table.find_all("th")] if table else []
    
    for tr in table.find_all("tr", recursive=False)[2:] if table else []:
        tables = tr.find_all("table")
        factors = [td.decode_contents() for td in tables[0].find_all("td")] if tables else []
        scores = [td.get_text(strip=True) for td in tables[1].find_all("td")] if len(tables) > 1 else []
        targets = [td.get_text(strip=True) for td in tables[2].find_all("td")] if len(tables) > 2 else []
        for factor, score, target in zip(factors, scores, targets):
            # Split score by comma if it contains one
            value = ""
            severity = ""
            if ',' in score:
                parts = score.split(',', 1)
                value = parts[0].strip() if len(parts) > 0 else ""
                severity = parts[1].strip() if len(parts) > 1 else ""
            else:
                value = score.strip()
                severity = ""

            if severity.lower() == "very high" or severity.lower() == "very low":
                high_values.append({
                    "factor": factor,
                    "severity": severity,
                    "score": value,
                    "target": target
                })
            entries.append({
                "factor": factor,
                "severity": severity,
                "score": value,
                "target": target
            })
            
    postface = []
    postface_div = table.find_next("div") if table else None
    for sibling in postface_div.next_siblings:
        if sibling.name == "small":
            postface.append(sibling.decode_contents())
    # postface = [small.get_text(strip=True) for small in postface_div_1.next_siblings("small", recursive=False)] if postface_div_1 else []

    return {
        "title": heading,
        "preface": preface,
        "score": total_score,
        "headers": headers,
        "factors": entries,
        "highValues": high_values,
        "postface": postface,
        "disclaimer": disclaimer_text,
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
        "intro": extract_intro(soup),
        "cognitive_assessment": extract_cognitive_assessment(soup),
        "stopbang": extract_stopbang(soup),
        "acb": extract_acb(soup),
        "leqembi": extract_leqembi(soup),
        "fall_risk": extract_fall_risk(soup),
        "additional_diagnostics": extract_additional_diagnostics(soup),
        "cognitiveFactors": extract_cognitive_factors(soup),
        "medicalIssues": extract_medical_issues(soup),
        "comorbidities": extract_comorbidities(soup),
        "reportedAndInferredComorbidities": extract_reported_and_inferred_comorbidities(soup),
        "currentMedications": extract_medications(soup),
        "immuneScore": extract_immune_score(soup),
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
