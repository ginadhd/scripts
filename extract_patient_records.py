#!/usr/bin/env python3
"""Extract patient records from OneNote .one files into CSV and TXT."""

import argparse
import csv
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Noise filter constants ---

FONT_NAMES = {"Calibri", "Calibri Light", "Arial", "Times New Roman", "Consolas"}
METADATA_TAGS = {"PageTitle", "PageDateTime", "cite", "blockquote", "code"}
SECTION_NAMES = {
    "Untitled Section",
    "Patient Demographics",
    "Patient Demographics.one",
    "Treatment Notes",
    "Open Notebook",
}

GUID_RE = re.compile(
    r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$", re.I
)
DAY_DATE_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s"
)
TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s+(AM|PM)$")
HYPERLINK_RE = re.compile(r"^HYPERLINK\s")

# --- Demographics constants ---

DEMOGRAPHICS_FIELDS = {
    "Date of Birth",
    "NHS Number",
    "Email Address",
    "Telephone Number",
    "Address",
}

DOB_TEXT_RE = re.compile(
    r"^\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}$"
)
DOB_NUMERIC_RE = re.compile(r"^(\d{2})[/\-](\d{2})[/\-](\d{4})$")
NHS_RE = re.compile(r"^(?:\d{3}\s+\d{3}\s+\d{4}|\d{10})$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^0[\d\s]{9,}$")
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}")

# --- Treatment notes constants ---

TREATMENT_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


# --- Core extraction functions ---


def extract_utf16le_strings(filepath):
    """Extract UTF-16LE encoded strings from a binary .one file."""
    try:
        data = filepath.read_bytes()
    except OSError as e:
        logger.error(f"Could not read {filepath}: {e}")
        return []
    matches = re.findall(b"(?:[\x20-\x7e]\x00){4,}", data)
    return [m.decode("utf-16-le") for m in matches]


def is_noise(s):
    """Check if a string is obvious metadata noise."""
    return (
        s in FONT_NAMES
        or s in METADATA_TAGS
        or s in SECTION_NAMES
        or bool(GUID_RE.match(s))
        or bool(DAY_DATE_RE.match(s))
        or bool(TIME_RE.match(s))
    )


def find_author_names(raw_strings, threshold=5):
    """Find strings appearing frequently — likely author/editor names."""
    candidates = [
        s for s in raw_strings if not is_noise(s) and s not in DEMOGRAPHICS_FIELDS
    ]
    counts = Counter(candidates)
    return {s for s, c in counts.items() if c >= threshold}


def process_hyperlink(s):
    """Extract display text from a HYPERLINK string."""
    m = re.match(r'HYPERLINK\s+"[^"]*"(.+)$', s)
    return m.group(1).strip() if m else None


def is_dob_value(s):
    """Check if a string looks like a date of birth value."""
    if DOB_TEXT_RE.match(s):
        return True
    m = DOB_NUMERIC_RE.match(s)
    if m:
        year = int(m.group(3))
        return 1900 <= year <= 2020
    return False


def extract_phone_number(s):
    """Extract a phone number, handling prefixes and annotations."""
    if PHONE_RE.match(s):
        return s
    m = re.search(r"(0\d[\d\s]{8,})", s)
    if m:
        number = re.sub(r"[^\d\s]+.*$", "", m.group(1)).strip()
        if PHONE_RE.match(number):
            return number
    return None


def filter_and_dedupe(raw_strings, author_names, extra_exclude=None):
    """Filter noise and author names, strip whitespace, remove consecutive dupes."""
    exclude = extra_exclude or set()
    filtered = []
    for s in raw_strings:
        if HYPERLINK_RE.match(s):
            display = process_hyperlink(s)
            if display:
                filtered.append(display)
            continue
        if is_noise(s) or s in author_names or s in exclude:
            continue
        stripped = s.strip()
        if stripped:
            filtered.append(stripped)

    # Remove consecutive duplicates
    deduped = []
    for s in filtered:
        if not deduped or s != deduped[-1]:
            deduped.append(s)
    return deduped


def remove_prefix_substrings(strings):
    """Remove strings that are a prefix of another string in the list.

    This eliminates OneNote's incremental-edit artifacts where partial
    versions of a string are saved alongside the final version.
    """
    string_set = set(strings)
    to_remove = set()
    for s in string_set:
        for other in string_set:
            if other != s and other.startswith(s) and len(other) > len(s):
                to_remove.add(s)
                break
    return [s for s in strings if s not in to_remove]


# --- Demographics ---


def extract_demographics(filepath, author_names):
    """Extract patient demographics from Untitled Section.one."""
    raw_strings = extract_utf16le_strings(filepath)
    if not raw_strings:
        return {}, {}

    deduped = filter_and_dedupe(raw_strings, author_names)
    deduped = remove_prefix_substrings(deduped)

    # Value extractors: return cleaned value or None
    extractors = {
        "Date of Birth": lambda s: s if is_dob_value(s) else None,
        "NHS Number": lambda s: s if NHS_RE.match(s) else None,
        "Email Address": lambda s: s if EMAIL_RE.match(s) else None,
        "Telephone Number": extract_phone_number,
        "Address": lambda s: s
        if (
            POSTCODE_RE.search(s)
            and len(s) > 15
            and not re.search(
                r"(Centre|Surgery|Practice|Health\s+Centre|Medical)", s, re.I
            )
        )
        else None,
    }

    demographics = {}

    # Strategy 1: label followed by an extracted value within a short window
    for field, extract in extractors.items():
        for i, s in enumerate(deduped):
            if s == field:
                for j in range(i + 1, min(i + 6, len(deduped))):
                    candidate = deduped[j]
                    if candidate not in DEMOGRAPHICS_FIELDS:
                        value = extract(candidate)
                        if value:
                            demographics[field] = value
                            break
                if field in demographics:
                    break

    # Strategy 2: address concatenation (when no single string has full address)
    if "Address" not in demographics:
        for i, s in enumerate(deduped):
            if s == "Address":
                parts = []
                for j in range(i + 1, min(i + 8, len(deduped))):
                    candidate = deduped[j]
                    if candidate in DEMOGRAPHICS_FIELDS:
                        break
                    parts.append(candidate)
                combined = " ".join(parts)
                if POSTCODE_RE.search(combined):
                    demographics["Address"] = combined
                    break

    # Strategy 3: direct pattern scan (last resort)
    found_values = set(demographics.values())
    for field, extract in extractors.items():
        if field not in demographics:
            for s in deduped:
                if s not in DEMOGRAPHICS_FIELDS and s not in found_values:
                    value = extract(s)
                    if value:
                        demographics[field] = value
                        found_values.add(value)
                        break

    # --- GP Practice info ---
    gp_info = _extract_gp_info(deduped, demographics, raw_strings)

    return demographics, gp_info


def _extract_gp_info(deduped, demographics, raw_strings):
    """Extract GP Practice details from the filtered string list."""
    gp_info = {}
    known = set(demographics.values()) | DEMOGRAPHICS_FIELDS

    # Collect patient phone numbers near "Telephone Number" labels
    patient_phones = set()
    for i, s in enumerate(deduped):
        if s == "Telephone Number":
            for j in range(i + 1, min(i + 4, len(deduped))):
                candidate = deduped[j]
                if candidate in DEMOGRAPHICS_FIELDS:
                    break
                phone = extract_phone_number(candidate)
                if phone:
                    patient_phones.add(phone.replace(" ", ""))
                    break  # only first phone per label

    for s in deduped:
        if s in known:
            continue
        if not gp_info.get("GP Practice") and re.search(
            r"(Medical|Centre|Surgery|Practice|Clinic|Health)", s, re.I
        ):
            gp_info["GP Practice"] = s
            continue
        if (
            not gp_info.get("GP Address")
            and POSTCODE_RE.search(s)
            and s != demographics.get("Address")
        ):
            gp_info["GP Address"] = s
            continue
        if not gp_info.get("GP Email") and s != demographics.get("Email Address"):
            email_candidate = s
            if s.lower().startswith("email:"):
                email_candidate = s.split(":", 1)[1].strip()
            if EMAIL_RE.match(email_candidate):
                gp_info["GP Email"] = email_candidate
                continue
        if not gp_info.get("GP Phone"):
            phone = extract_phone_number(s)
            if phone:
                norm = phone.replace(" ", "")
                patient_norm = demographics.get("Telephone Number", "").replace(" ", "")
                if norm != patient_norm and norm not in patient_phones:
                    gp_info["GP Phone"] = phone

    # Try extracting GP phone from HYPERLINK display text
    if not gp_info.get("GP Phone"):
        for s in raw_strings:
            if HYPERLINK_RE.match(s):
                m = re.match(r'HYPERLINK\s+"[^"]*"(.+)$', s)
                if m:
                    display = m.group(1).strip()
                    patient_phone = demographics.get("Telephone Number", "")
                    if (
                        PHONE_RE.match(display)
                        and display.replace(" ", "") != patient_phone.replace(" ", "")
                    ):
                        gp_info["GP Phone"] = display
                        break

    return gp_info


# --- Treatment Notes ---


def extract_treatment_notes(filepath, author_names):
    """Extract treatment notes from Treatment Notes.one."""
    raw_strings = extract_utf16le_strings(filepath)
    if not raw_strings:
        return []

    deduped = filter_and_dedupe(
        raw_strings, author_names, extra_exclude={"Treatment Notes"}
    )
    deduped = remove_prefix_substrings(deduped)

    # Group entries by date headers
    groups = []  # list of (date_str, [entries])
    current_date = None
    current_entries = []

    for s in deduped:
        if TREATMENT_DATE_RE.match(s):
            if current_date is not None:
                groups.append((current_date, current_entries))
            current_date = s
            current_entries = []
        elif current_date is not None:
            current_entries.append(s)
        else:
            # Entries appearing before any date
            current_entries.append(s)

    # Flush last group
    if current_date is not None and current_entries:
        groups.append((current_date, current_entries))
    elif current_entries:
        groups.append(("Undated", current_entries))

    # Merge entries sharing the same date, preserving first-seen order
    merged = {}
    date_order = []
    for date, entries in groups:
        if date not in merged:
            merged[date] = []
            date_order.append(date)
        for entry in entries:
            if entry not in merged[date]:
                merged[date].append(entry)

    notes = [(d, merged[d]) for d in date_order]

    # Sort chronologically (dd/mm/yyyy)
    def _parse_date(date_str):
        try:
            return datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            return datetime.max

    notes.sort(key=lambda x: _parse_date(x[0]))

    return notes


# --- Output writers ---


DEMOGRAPHICS_COLUMNS = [
    "Patient Name",
    "Date of Birth",
    "NHS Number",
    "Email Address",
    "Telephone Number",
    "Address",
    "GP Practice",
    "GP Address",
    "GP Phone",
    "GP Email",
]


def write_demographics_csv(patient_name, demographics, gp_info, output_path):
    """Write demographics to a CSV with one row per patient."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_fields = {"Patient Name": patient_name, **demographics, **gp_info}
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(DEMOGRAPHICS_COLUMNS)
        writer.writerow([all_fields.get(col, "") for col in DEMOGRAPHICS_COLUMNS])


def write_treatment_notes_txt(notes, output_path):
    """Write treatment notes to a plain text file with date headers."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for date, entries in notes:
            f.write(f"--- {date} ---\n")
            for entry in entries:
                f.write(f"{entry}\n")
            f.write("\n")


# --- Main ---


def main():
    parser = argparse.ArgumentParser(
        description="Extract patient records from OneNote .one files."
    )
    parser.add_argument(
        "input_folder", help="Path to parent folder containing patient subfolders"
    )
    parser.add_argument(
        "--output", default="/documents", help="Output directory (default: /documents)"
    )
    args = parser.parse_args()

    input_path = Path(args.input_folder)
    output_path = Path(args.output)

    if not input_path.is_dir():
        logger.error(f"Input folder does not exist: {input_path}")
        return

    processed = 0
    skipped = 0

    for patient_folder in sorted(input_path.iterdir()):
        if not patient_folder.is_dir():
            continue

        records_dir = patient_folder / "Personal Patient Records Template"
        if not records_dir.is_dir():
            logger.warning(
                f'Skipping "{patient_folder.name}": '
                f"no Personal Patient Records Template subfolder"
            )
            skipped += 1
            continue

        demographics_file = records_dir / "Untitled Section.one"
        treatment_file = records_dir / "Treatment Notes.one"
        patient_name = patient_folder.name
        patient_output = output_path / patient_name

        # Detect author names across both files for robust filtering
        all_strings = []
        for fp in (demographics_file, treatment_file):
            if fp.exists():
                all_strings.extend(extract_utf16le_strings(fp))
        author_names = find_author_names(all_strings)

        # Demographics
        if demographics_file.exists():
            demographics, gp_info = extract_demographics(
                demographics_file, author_names
            )
            write_demographics_csv(
                patient_name, demographics, gp_info,
                patient_output / "patient_demographics.csv",
            )
            logger.info(
                f"{patient_name}: {len(demographics)} demographics, "
                f"{len(gp_info)} GP fields"
            )
        else:
            logger.warning(f"{patient_name}: missing Untitled Section.one")

        # Treatment notes
        if treatment_file.exists():
            notes = extract_treatment_notes(treatment_file, author_names)
            write_treatment_notes_txt(
                notes, patient_output / "treatment_notes.txt"
            )
            total = sum(len(e) for _, e in notes)
            logger.info(
                f"{patient_name}: {len(notes)} note groups ({total} entries)"
            )
        else:
            logger.warning(f"{patient_name}: missing Treatment Notes.one")

        processed += 1

    logger.info(f"Done: {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    main()
