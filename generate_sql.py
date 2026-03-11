#!/usr/bin/env python3
"""Generate SQL INSERT statements for mhs001_mpi and mhs002_gp from patient CSV."""

import argparse
import csv
import re

POSTCODE_RE = re.compile(r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\s*$", re.I)
SURNAME_PREFIXES = {"de", "di", "la", "le", "van", "von", "o'"}


def split_name(full_name):
    """Split full name into (first_name, last_name)."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name.strip(), ""
    if len(parts) == 2:
        return parts[0], parts[1]
    # Check if second-to-last word is a surname prefix like De, O', etc.
    if parts[-2].lower() in SURNAME_PREFIXES:
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    # Default: last word is surname, rest is first name(s)
    return " ".join(parts[:-1]), parts[-1]


def parse_date(date_str):
    """Convert dd/mm/yyyy to YYYY-MM-DD for PostgreSQL."""
    if not date_str or not date_str.strip():
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", date_str.strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def parse_address(address_str):
    """Extract (address_line_1, postcode) from a full address string."""
    if not address_str or not address_str.strip():
        return None, None
    addr = address_str.strip()
    m = POSTCODE_RE.search(addr)
    postcode = None
    if m:
        postcode = m.group(1).upper().strip()
        # Ensure postcode has a space before the last 3 chars
        if " " not in postcode:
            postcode = postcode[:-3] + " " + postcode[-3:]
        addr = addr[: m.start()].strip().rstrip(",").strip()
    return addr or None, postcode


def sql_val(value):
    """Format a Python value as a SQL literal."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(
        description="Generate SQL inserts from patient demographics CSV."
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default="documents/all_patients.csv",
        help="Path to merged CSV (default: documents/all_patients.csv)",
    )
    parser.add_argument(
        "--output",
        default="documents/seed_patients.sql",
        help="Output SQL file (default: documents/seed_patients.sql)",
    )
    args = parser.parse_args()

    with open(args.csv_file, newline="") as f:
        patients = list(csv.DictReader(f))

    lines = [
        "-- Patient seed data generated from extracted OneNote records",
        "-- Review before running against the database",
        "",
        "BEGIN;",
        "",
        "-- =============================================================",
        "-- mhs001_mpi  (Master Patient Index)",
        "-- =============================================================",
        "",
    ]

    seen_nhs = set()
    skipped = []

    for p in patients:
        nhs = p["NHS Number"].replace(" ", "")
        if nhs in seen_nhs:
            skipped.append((p["Patient Name"], nhs))
            continue
        seen_nhs.add(nhs)

        first_name, last_name = split_name(p["Patient Name"])
        dob = parse_date(p["Date of Birth"])
        phone = p.get("Telephone Number", "").strip() or None
        email = p.get("Email Address", "").strip() or None
        addr_line, postcode = parse_address(p.get("Address", ""))

        lines.append(
            f"INSERT INTO mhs001_mpi "
            f"(nhs_number, first_name, last_name, date_of_birth, "
            f"phone_number, email, address_line_1, postcode)\n"
            f"VALUES ({sql_val(nhs)}, {sql_val(first_name)}, {sql_val(last_name)}, "
            f"{sql_val(dob)}, {sql_val(phone)}, {sql_val(email)}, "
            f"{sql_val(addr_line)}, {sql_val(postcode)})\n"
            f"ON CONFLICT (nhs_number) DO UPDATE SET\n"
            f"  first_name = EXCLUDED.first_name,\n"
            f"  last_name = EXCLUDED.last_name,\n"
            f"  date_of_birth = EXCLUDED.date_of_birth,\n"
            f"  phone_number = EXCLUDED.phone_number,\n"
            f"  email = EXCLUDED.email,\n"
            f"  address_line_1 = EXCLUDED.address_line_1,\n"
            f"  postcode = EXCLUDED.postcode;"
        )
        lines.append("")

    if skipped:
        lines.append("-- SKIPPED (duplicate NHS number):")
        for name, nhs in skipped:
            lines.append(f"--   {name} ({nhs})")
        lines.append("")

    lines.extend(
        [
            "-- =============================================================",
            "-- mhs002_gp  (GP Registration)",
            "-- =============================================================",
            "",
        ]
    )

    seen_nhs_gp = set()
    for p in patients:
        nhs = p["NHS Number"].replace(" ", "")
        if nhs in seen_nhs_gp:
            continue
        seen_nhs_gp.add(nhs)

        gp_name = p.get("GP Practice", "").strip() or None
        gp_email = p.get("GP Email", "").strip() or None

        if gp_name:
            lines.append(
                f"INSERT INTO mhs002_gp "
                f"(nhs_number, gmp_code_reg, gp_practice_name, gp_contact_email)\n"
                f"SELECT {sql_val(nhs)}, 'V81999', {sql_val(gp_name)}, {sql_val(gp_email)}\n"
                f"WHERE NOT EXISTS (SELECT 1 FROM mhs002_gp WHERE nhs_number = {sql_val(nhs)});"
            )
            lines.append("")

    lines.append("COMMIT;")
    lines.append("")

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated {args.output}: {len(seen_nhs)} patients, {len(skipped)} skipped")
    for name, nhs in skipped:
        print(f"  DUPLICATE: {name} (NHS {nhs})")


if __name__ == "__main__":
    main()
