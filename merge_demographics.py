#!/usr/bin/env python3
"""Merge individual patient demographics CSVs into a single CSV."""

import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Merge patient demographics CSVs into one file."
    )
    parser.add_argument(
        "documents_folder", help="Path to documents folder containing patient subfolders"
    )
    parser.add_argument(
        "--output", default="all_patients.csv", help="Output CSV path (default: all_patients.csv)"
    )
    args = parser.parse_args()

    docs = Path(args.documents_folder)
    rows = []
    headers = None

    for csv_file in sorted(docs.glob("*/patient_demographics.csv")):
        with open(csv_file, newline="") as f:
            reader = csv.reader(f)
            file_headers = next(reader)
            if headers is None:
                headers = file_headers
            for row in reader:
                rows.append(row)

    if not rows:
        print("No patient demographics found.")
        return

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Merged {len(rows)} patients into {args.output}")


if __name__ == "__main__":
    main()
