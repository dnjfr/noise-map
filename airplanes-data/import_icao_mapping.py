#!/usr/bin/env python3
"""Extract ICAO type code → aircraft model mapping from FAA JO 7360.1H PDF.

Parsing strategy (based on coordinate analysis of the PDF):
- Page width: 612pt. MANUFACTURER column starts at x ≈ 289.
- Each ICAO code row is in the left columns (x < 285).
- Each MANUFACTURER, Model row is in the right column (x >= 285).
- Within a page, the ICAO code row is vertically centered among its model rows
  (some model rows appear ABOVE the code row, some below).
- Assignment: each model row is assigned to the nearest ICAO code by y distance.
- Cross-page: orphaned model rows at the top of a page belong to the last code
  from the previous page (tracked via prev_context).

Known limitation: some MAdB model names use variant suffixes (e.g. "A321-253N")
while this PDF uses commercial names ("A-321neo"). A fuzzy/regex matching layer
will be needed when joining with madb_noise_ref.
"""

import os
import re
import sys

import psycopg
import pdfplumber

PDF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "2023-03-24_Order_JO_7360.1H_Aircraft_Type_Designators_FINAL_SIGNED.pdf",
)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "noise_map"),
    "user": os.environ.get("DB_USER", "noiseuser"),
    "password": os.environ.get("DB_PASSWORD", "noisepass"),
}

# Appendix A spans pages 11-370 in the PDF (0-indexed: 10-369)
APPENDIX_A_START = 10
APPENDIX_A_END = 370

AIRCRAFT_CLASSES = (
    "Fixed-wing", "Helicopter", "Gyrocopter", "Amphibian",
    "Tiltrotor", "Balloon", "Airship",
)
_CLASSES_ALT = "|".join(AIRCRAFT_CLASSES)

# ICAO code: 1-4 uppercase/digit chars, optional * or @ prefix/suffix
ICAO_CODE_RE = re.compile(r'^@?([A-Z0-9]{1,4})\*?$')
CLASS_RE = re.compile(r'^(' + _CLASSES_ALT + r')$')
WTC_RE = re.compile(r'\b(Light|Medium|Heavy|Super)\b')

# Manufacturer: all-uppercase word(s) before the comma
# e.g. "BOEING", "DE HAVILLAND", "JIANGXI CHANGHE-AGUSTA", "3XTRIM"
MANUF_RE = re.compile(r'^[A-Z0-9][A-Z0-9 \-\(\)&.\'/+]{1,}$')

# x threshold: MANUFACTURER column starts at ~289 on a 612pt page
MANUF_X_THRESHOLD = 285

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS icao_type_mapping (
    id SERIAL PRIMARY KEY,
    icao_code    VARCHAR(10)  NOT NULL,
    manufacturer VARCHAR(200),
    model        VARCHAR(300) NOT NULL,
    aircraft_class VARCHAR(50),
    wtc          VARCHAR(10),
    UNIQUE(icao_code, manufacturer, model)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_icao_type_code ON icao_type_mapping(icao_code);
"""

INSERT_SQL = """
INSERT INTO icao_type_mapping (icao_code, manufacturer, model, aircraft_class, wtc)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (icao_code, manufacturer, model) DO NOTHING
"""


def group_by_row(words, y_tolerance=3):
    """Group pdfplumber word dicts into rows keyed by y position."""
    rows = {}
    for word in words:
        y = word["top"]
        matched = None
        for ey in rows:
            if abs(ey - y) <= y_tolerance:
                matched = ey
                break
        key = matched if matched is not None else y
        rows.setdefault(key, []).append(word)
    return {y: sorted(ws, key=lambda w: w["x0"]) for y, ws in sorted(rows.items())}


def parse_page(page, prev_context=None):
    """
    Parse one page of Appendix A.

    Returns:
        entries: list of (icao_code, manufacturer, model, aircraft_class, wtc)
        last_context: (icao_code, aircraft_class, wtc) of the last ICAO code seen
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return [], prev_context

    rows = group_by_row(words)

    # Collect ICAO code positions and model positions separately
    icao_at = {}    # y -> (code, class, wtc)
    model_at = {}   # y -> (manufacturer, model_text)

    for y, row_words in rows.items():
        left_words = [w for w in row_words if w["x0"] < MANUF_X_THRESHOLD]
        right_words = [w for w in row_words if w["x0"] >= MANUF_X_THRESHOLD]

        # Detect ICAO code in left column
        if len(left_words) >= 2:
            first = left_words[0]["text"]
            second = left_words[1]["text"]
            m_code = ICAO_CODE_RE.match(first)
            if m_code and CLASS_RE.match(second):
                code = m_code.group(1)
                cls = second
                left_text = " ".join(w["text"] for w in left_words)
                wtc_m = WTC_RE.search(left_text)
                wtc = wtc_m.group(1) if wtc_m else None
                icao_at[y] = (code, cls, wtc)

        # Detect MANUFACTURER, Model in right column
        if right_words:
            right_text = " ".join(w["text"] for w in right_words)
            comma_idx = right_text.find(",")
            if comma_idx > 1:
                manuf = right_text[:comma_idx].strip()
                model_text = right_text[comma_idx + 1:].strip()
                if model_text and MANUF_RE.match(manuf):
                    model_at[y] = (manuf, model_text)

    if not model_at:
        last_ctx = prev_context
        if icao_at:
            last_ctx = icao_at[max(icao_at)]
        return [], last_ctx

    # Build lookup: all known ICAO y-positions including a virtual one for
    # the previous page's context (handles orphaned models at top of page)
    all_icao_ys = sorted(icao_at.keys())
    extended_icao = dict(icao_at)

    if prev_context and (not all_icao_ys or min(all_icao_ys) > 80):
        # Place the previous context at y=0 (above everything on this page)
        extended_icao[0] = prev_context
        all_icao_ys = [0] + all_icao_ys

    # Assign each model row to its ICAO code using a ratio-based heuristic:
    # - For a model between code C1 (above) and C2 (below):
    #   - d_above = model_y - C1_y, d_below = C2_y - model_y
    #   - if d_below / d_above > 2.0 → post-code model of C1 (assign to C1)
    #   - else                        → pre-code model of C2  (assign to C2)
    # This correctly handles cases where C1 has few models and C2's first model
    # ends up closer to C1 than to C2 by simple distance.
    RATIO_THRESHOLD = 2.0
    entries = []
    if all_icao_ys:
        for model_y, (manuf, model_text) in model_at.items():
            # Skip page header row
            if manuf == "MANUFACTURER":
                continue

            above_ys = [y for y in all_icao_ys if y <= model_y]
            below_ys = [y for y in all_icao_ys if y > model_y]

            if not above_ys:
                assigned_y = below_ys[0]
            elif not below_ys:
                assigned_y = above_ys[-1]
            else:
                nearest_above = above_ys[-1]
                nearest_below = below_ys[0]
                d_above = model_y - nearest_above
                d_below = nearest_below - model_y
                if d_above == 0 or d_below / d_above > RATIO_THRESHOLD:
                    assigned_y = nearest_above  # post-code model
                else:
                    assigned_y = nearest_below  # pre-code model

            code, cls, wtc = extended_icao[assigned_y]
            entries.append((code, manuf, model_text, cls, wtc))

    # Last real ICAO context on this page
    last_ctx = prev_context
    real_ys = [y for y in icao_at]
    if real_ys:
        last_ctx = icao_at[max(real_ys)]

    return entries, last_ctx


def extract_all(pdf_path):
    all_entries = []
    prev_context = None

    with pdfplumber.open(pdf_path) as pdf:
        end = min(APPENDIX_A_END, len(pdf.pages))
        total = end - APPENDIX_A_START
        for i, page_num in enumerate(range(APPENDIX_A_START, end)):
            if i % 50 == 0:
                print(f"  Page {page_num + 1}/{end}  ({i}/{total})...", flush=True)
            page = pdf.pages[page_num]
            entries, prev_context = parse_page(page, prev_context)
            all_entries.extend(entries)

    return all_entries


def main():
    print(f"PDF : {PDF_PATH}", flush=True)
    if not os.path.exists(PDF_PATH):
        print(f"ERREUR : PDF introuvable", file=sys.stderr)
        sys.exit(1)

    print("Extraction en cours...", flush=True)
    raw = extract_all(PDF_PATH)
    print(f"  Brut : {len(raw)} entrées", flush=True)

    # Dédoublonnage
    seen = set()
    entries = []
    for icao_code, manuf, model, cls, wtc in raw:
        key = (icao_code, manuf, model)
        if key not in seen:
            seen.add(key)
            entries.append((icao_code, manuf, model, cls, wtc))
    print(f"  Uniques : {len(entries)} entrées", flush=True)

    print("Connexion à la base...", flush=True)
    conn = psycopg.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_INDEX_SQL)
            inserted = skipped = 0
            for entry in entries:
                cur.execute(INSERT_SQL, entry)
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
        conn.commit()
        print(f"  {inserted} insérés, {skipped} ignorés (doublons)", flush=True)
        print("Import terminé.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
