import re
import csv
from typing import List, Dict, Optional


# # Load biomedical model
# nlp = spacy.load("en_ner_bionlp13cg_md")

# # Common risk / qualifier terms
# RISK_TERMS = [
#     "high", "low", "elevated", "normal", "decreased", "increased",
#     "below target", "above target", "far below target", "far above target",
#     "possible", "borderline", "suspected", "abnormal",
#     "within range", "within normal limits"
# ]

# # Common units
# UNIT_PATTERN = r"(?:%|pg/mL|mg/dL|mmol/L|µg/L|μg/L|ng/mL|mEq/L|IU/L|U/L|g/dL)"

# # Pattern for direct (linear) risk + value phrases
# LINEAR_PATTERN = re.compile(
#     rf"(?i)({'|'.join(RISK_TERMS)})\s+([\w\s\-\βτ™]+?)\s+([\d.]+(?:\s?{UNIT_PATTERN})?)"
# )


# def extract_stage(text: str) -> Optional[str]:
#     """Extract disease stage (e.g. 'stage 3a')."""
#     stage_match = re.search(r"stage\s*([0-9]+[a-z]?)", text, re.I)
#     return stage_match.group(1).lower() if stage_match else None


# def extract_medical_info_spacy(text: str) -> List[Dict[str, Optional[str]]]:
#     doc = nlp(text)
#     results = []

#     # 1️⃣ Direct linear pattern matches (e.g. 'high TSH 3.0')
#     for risk, name, value in LINEAR_PATTERN.findall(text):
#         unit_match = re.search(UNIT_PATTERN, value)
#         unit = unit_match.group(0) if unit_match else None
#         clean_value = re.sub(UNIT_PATTERN, "", value).strip()
#         results.append({
#             "name": name.strip(),
#             "value": clean_value,
#             "unit": unit,
#             "risk": risk.lower(),
#             "stage": extract_stage(text)
#         })

#     # 2️⃣ Entity-based matching for complex cases
#     for ent in doc.ents:
#         if ent.label_ in ["CHEMICAL", "DISEASE", "GENE_OR_GENE_PRODUCT"]:
#             window = doc[max(ent.start - 8, 0):min(ent.end + 10, len(doc))]
#             window_text = window.text

#             # Risk near entity
#             risk_match = re.search(rf"(?i)({'|'.join(RISK_TERMS)})", window_text)
#             risk = risk_match.group(1).lower() if risk_match else None

#             # Value + unit
#             val_match = re.search(rf"([\d.]+)\s?({UNIT_PATTERN})?", window_text)
#             value, unit = None, None
#             if val_match:
#                 value = val_match.group(1)
#                 unit = val_match.group(2) or None

#             # Stage near entity
#             stage = extract_stage(window_text)

#             # Handle biomarkers lists
#             if not (value or risk or stage):
#                 if "," in window_text or "&" in window_text:
#                     results.append({
#                         "name": ent.text.strip(),
#                         "value": None,
#                         "unit": None,
#                         "risk": None,
#                         "stage": None
#                     })
#                     continue

#             if risk or value or stage:
#                 results.append({
#                     "name": ent.text.strip(),
#                     "value": value,
#                     "unit": unit,
#                     "risk": risk,
#                     "stage": stage
#                 })

#     # 3️⃣ Deduplicate
#     unique = []
#     seen = set()
#     for item in results:
#         key = (item.get("name"), item.get("value"), item.get("risk"), item.get("stage"))
#         if key not in seen:
#             seen.add(key)
#             unique.append(item)

#     return unique

RISK_TERMS = [
    "high", "low", "elevated", "normal", "decreased", "increased",
    "below target", "above target", "far below target", "far above target",
    "possible", "borderline", "suspected", "abnormal",
    "within range", "within normal limits"
]

UNIT_PATTERN = r"(?:%|pg/mL|mg/dL|mmol/L|µg/L|μg/L|ng/mL|mEq/L|IU/L|U/L|g/dL)"
STAGE_PATTERN = r"stage\s*([0-9]+[a-z]?)"

# 🧬 Load biomedical terms & synonyms from CSV
def load_biomedical_terms(csv_path: str) -> List[str]:
    terms = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            terms.append(row['term'].strip().lower())
            if row.get('synonyms'):
                for syn in row['synonyms'].split(';'):
                    terms.append(syn.strip().lower())
    return sorted(set(filter(None, terms)))

def extract_stage(text: str) -> Optional[str]:
    m = re.search(STAGE_PATTERN, text, re.I)
    return m.group(1).lower() if m else None

def extract_risk_tokens(text: str, known_terms: List[str]) -> List[Dict[str, Optional[str]]]:
    findings = []
    stage = extract_stage(text)
    if stage:
        # Remove stage from text to avoid confusion
        text = re.sub(STAGE_PATTERN, "", text, flags=re.I).strip()
        
    text = re.sub(STAGE_PATTERN, "", text, flags=re.I).strip()
        
    segments = re.split(r"[,;&]|\.\s", text)

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        # Match against known terms
        name = None
        for term in known_terms:
            if re.search(rf"\b{re.escape(term)}\b", seg, re.I):
                name = term
                seg = re.sub(rf"\b{re.escape(term)}\b", "", seg, flags=re.I).strip()
                break
            
        risk_match = re.search(rf"(?i)\b({'|'.join(RISK_TERMS)})\b", seg)
        risk = risk_match.group(1).lower() if risk_match else None

        val_match = re.search(rf"([\d]+(?:\.[\d]+)?)\s*({UNIT_PATTERN})?", seg)
        # if(val_match):
        #     if val_match.group(1):
        #         print("Match: ", val_match.group(1))
        #     if val_match.group(2):
        #         print("Unit: ", val_match.group(2))
        value = val_match.group(1) if val_match else None
        unit = val_match.group(2) if val_match else None
        if(name is None and len(findings) > 0 and (value or unit)):
            if findings[-1]["value"] is None:
                findings[-1]["value"] = value
            if findings[-1]["unit"] is None:
                findings[-1]["unit"] = unit

        # Fallback: pick capitalized tokens
        # if not name:
        #     capital = re.findall(r"\b[A-Z][A-Za-z0-9\-]+(?:\s[A-Z][A-Za-z0-9\-]+)*\b", seg)
        #     if capital:
        #         name = capital[0]

        if any([name, value, risk, stage]):
            findings.append({
                "name": name,
                "value": value,
                "unit": unit,
                "risk": risk,
                "stage": stage
            })

    return findings