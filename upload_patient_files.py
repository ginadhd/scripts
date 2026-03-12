#!/usr/bin/env python3
"""
upload_patient_files.py — Upload patient files to Azure Blob Storage.

Reads patient folders under a root directory, matches each folder name
to an NHS number via all_patients.csv, and uploads every non-OneNote file
into the 'patient-forms' container using the blob key pattern:

    {nhsNumber}/{YYYY-MM-DD}-{uuid8}-{sanitized_filename}

Excludes: .one, .onetoc2 files and the Personal Patient Records Template folder.

Usage:
    uv run upload_patient_files.py <patient-files-dir> <all_patients.csv>

Credentials loaded from scripts/.env via pydantic-settings.
"""

import csv
import logging
import mimetypes
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from azure.storage.blob import BlobServiceClient, ContentSettings
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Silence verbose Azure SDK logging
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

CONTAINER_NAME = "patient-forms"
UPLOADER_ID = "bulk-import"
UPLOADER_NAME = "Bulk Import"
UPLOADER_TYPE = "staff"

EXCLUDED_EXTENSIONS = {".one", ".onetoc2"}
EXCLUDED_DIRS = {"Personal Patient Records"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    AZURE_STORAGE_CONNECTION_STRING: str


def sanitize_filename(name):
    return re.sub(r"[^a-zA-Z0-9.\-]", "_", name)


def generate_blob_key(nhs_number, filename):
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    short_uuid = uuid.uuid4().hex[:8]
    safe_name = sanitize_filename(filename)
    return f"{nhs_number}/{date_prefix}-{short_uuid}-{safe_name}"


def detect_content_type(filepath):
    mime, _ = mimetypes.guess_type(filepath)
    return mime or "application/octet-stream"


def build_metadata(original_filename):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "originalfilename": quote(original_filename, safe=""),
        "uploadedby": UPLOADER_ID,
        "uploadername": quote(UPLOADER_NAME, safe=""),
        "uploadertype": UPLOADER_TYPE,
        "uploadedat": now,
    }


def build_patient_lookup(csv_path):
    """Build lookup: folder name (Patient Name or Folder Name) → NHS number."""
    lookup = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nhs = row["NHS Number"].replace(" ", "")
            name = row["Patient Name"].strip()
            if name not in lookup:
                lookup[name] = nhs
            # Also index by Folder Name if present (batch 2 uses Lastname_First_DOB)
            folder = row.get("Folder Name", "").strip()
            if folder and folder not in lookup:
                lookup[folder] = nhs
    return lookup


def collect_files(folder):
    """Collect all uploadable files, excluding OneNote files and template folder."""
    files = []
    for item in sorted(folder.rglob("*")):
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        if item.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue
        if any(
                part.startswith(excluded) for part in item.parts for excluded in EXCLUDED_DIRS
            ):
                continue
        files.append(item)
    return files


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <patient-files-dir> <all_patients.csv>", file=sys.stderr)
        sys.exit(1)

    files_dir = Path(sys.argv[1])
    csv_path = Path(sys.argv[2])

    if not files_dir.is_dir():
        print(f"Error: directory not found: {files_dir}", file=sys.stderr)
        sys.exit(1)
    if not csv_path.is_file():
        print(f"Error: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    settings = Settings()
    lookup = build_patient_lookup(csv_path)
    logger.info(f"Loaded {len(lookup)} patients from CSV")

    service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    container_client = service_client.get_container_client(CONTAINER_NAME)

    uploaded = 0
    failed = 0
    failed_files = []
    skipped_folders = []

    folders = [f for f in sorted(files_dir.iterdir()) if f.is_dir()]
    total_folders = len(folders)

    for folder_idx, folder in enumerate(folders, 1):
        patient_name = folder.name
        nhs_number = lookup.get(patient_name)

        if nhs_number is None:
            skipped_folders.append((patient_name, "no CSV match"))
            logger.debug(f"[{folder_idx}/{total_folders}] Skipped {patient_name}: no CSV match")
            continue

        files = collect_files(folder)
        if not files:
            skipped_folders.append((patient_name, "no uploadable files"))
            logger.debug(f"[{folder_idx}/{total_folders}] Skipped {patient_name}: no uploadable files")
            continue

        logger.info(f"[{folder_idx}/{total_folders}] {patient_name} -> {nhs_number} ({len(files)} files)")

        for filepath in files:
            blob_key = generate_blob_key(nhs_number, filepath.name)
            content_type = detect_content_type(str(filepath))
            metadata = build_metadata(filepath.name)

            try:
                with open(filepath, "rb") as f:
                    data = f.read()

                blob_client = container_client.get_blob_client(blob_key)
                blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=ContentSettings(content_type=content_type),
                    metadata=metadata,
                )
                uploaded += 1
                logger.info(f"  OK {filepath.name}")
            except Exception as e:
                failed += 1
                failed_files.append((patient_name, filepath.name, str(e)))
                logger.error(f"  FAIL {filepath.name}: {e}")

    logger.info(f"Done: {uploaded} uploaded, {failed} failed, {len(skipped_folders)} folders skipped")
    if failed_files:
        logger.error(f"Failed uploads ({failed}):")
        for name, fname, err in failed_files:
            logger.error(f"  {name}/{fname}: {err}")
    if skipped_folders:
        logger.info(f"Skipped {len(skipped_folders)} folders:")
        for name, reason in skipped_folders:
            logger.info(f"  - {name}: {reason}")


if __name__ == "__main__":
    main()
