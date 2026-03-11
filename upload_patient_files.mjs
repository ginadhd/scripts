/**
 * upload_patient_files.mjs — Upload patient files to Azure Blob Storage.
 *
 * Usage (on API pod):
 *   node /tmp/upload/upload_patient_files.mjs /tmp/upload/patients /tmp/upload/all_patients.csv
 *
 * Reads AZURE_STORAGE_CONNECTION_STRING from environment.
 */

import { BlobServiceClient } from "@azure/storage-blob";
import { readFileSync, readdirSync, statSync } from "fs";
import { join, extname } from "path";
import { randomUUID } from "crypto";

const CONTAINER_NAME = "patient-forms";
const UPLOADER_ID = "bulk-import";
const UPLOADER_NAME = "Bulk Import";
const UPLOADER_TYPE = "staff";
const EXCLUDED_EXTENSIONS = new Set([".one", ".onetoc2"]);
const EXCLUDED_DIRS = new Set(["Personal Patient Records Template"]);

const MIME_TYPES = {
  ".pdf": "application/pdf",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".doc": "application/msword",
  ".rtf": "application/rtf",
  ".txt": "text/plain",
  ".csv": "text/csv",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

function sanitizeFilename(name) {
  return name.replace(/[^a-zA-Z0-9.\-]/g, "_");
}

function generateBlobKey(nhsNumber, filename) {
  const date = new Date().toISOString().slice(0, 10);
  const shortUuid = randomUUID().replace(/-/g, "").slice(0, 8);
  return `${nhsNumber}/${date}-${shortUuid}-${sanitizeFilename(filename)}`;
}

function detectContentType(filepath) {
  const ext = extname(filepath).toLowerCase();
  return MIME_TYPES[ext] || "application/octet-stream";
}

function buildMetadata(originalFilename) {
  return {
    originalfilename: encodeURIComponent(originalFilename),
    uploadedby: UPLOADER_ID,
    uploadername: encodeURIComponent(UPLOADER_NAME),
    uploadertype: UPLOADER_TYPE,
    uploadedat: new Date().toISOString(),
  };
}

function parseCSV(csvPath) {
  const content = readFileSync(csvPath, "utf-8");
  const lines = content.trim().split("\n");
  const headers = lines[0].split(",").map((h) => h.trim());
  const lookup = new Map();

  for (let i = 1; i < lines.length; i++) {
    // Simple CSV parse handling quoted fields
    const row = [];
    let current = "";
    let inQuotes = false;
    for (const ch of lines[i]) {
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === "," && !inQuotes) {
        row.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    row.push(current.trim());

    const nameIdx = headers.indexOf("Patient Name");
    const nhsIdx = headers.indexOf("NHS Number");
    if (nameIdx >= 0 && nhsIdx >= 0) {
      const name = row[nameIdx];
      const nhs = row[nhsIdx].replace(/\s/g, "");
      if (name && !lookup.has(name)) {
        lookup.set(name, nhs);
      }
    }
  }
  return lookup;
}

function collectFiles(dir) {
  const files = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!EXCLUDED_DIRS.has(entry.name)) {
        files.push(...collectFiles(fullPath));
      }
    } else if (entry.isFile()) {
      if (!entry.name.startsWith(".") && !EXCLUDED_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
        files.push(fullPath);
      }
    }
  }
  return files.sort();
}

async function main() {
  const [filesDir, csvPath] = process.argv.slice(2);
  if (!filesDir || !csvPath) {
    console.error("Usage: node upload_patient_files.mjs <patient-files-dir> <all_patients.csv>");
    process.exit(1);
  }

  const connStr = process.env.AZURE_STORAGE_CONNECTION_STRING;
  if (!connStr) {
    console.error("Error: AZURE_STORAGE_CONNECTION_STRING not set");
    process.exit(1);
  }

  const lookup = parseCSV(csvPath);
  console.log(`Loaded ${lookup.size} patients from CSV`);

  const blobService = BlobServiceClient.fromConnectionString(connStr);
  const container = blobService.getContainerClient(CONTAINER_NAME);

  let uploaded = 0;
  const skipped = [];

  const folders = readdirSync(filesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .sort((a, b) => a.name.localeCompare(b.name));

  for (const folder of folders) {
    const patientName = folder.name;
    const nhsNumber = lookup.get(patientName);

    if (!nhsNumber) {
      skipped.push([patientName, "no CSV match"]);
      continue;
    }

    const folderPath = join(filesDir, folder.name);
    const files = collectFiles(folderPath);

    if (files.length === 0) {
      skipped.push([patientName, "no uploadable files"]);
      continue;
    }

    console.log(`\n${patientName} -> ${nhsNumber} (${files.length} files)`);

    for (const filepath of files) {
      const filename = filepath.split("/").pop();
      const blobKey = generateBlobKey(nhsNumber, filename);
      const contentType = detectContentType(filepath);
      const metadata = buildMetadata(filename);
      const data = readFileSync(filepath);

      const blobClient = container.getBlockBlobClient(blobKey);
      await blobClient.upload(data, data.length, {
        blobHTTPHeaders: { blobContentType: contentType },
        metadata,
      });

      uploaded++;
      console.log(`  + ${filename} -> ${blobKey}`);
    }
  }

  console.log(`\nDone: ${uploaded} files uploaded`);
  if (skipped.length > 0) {
    console.log(`\nSkipped ${skipped.length} folders:`);
    for (const [name, reason] of skipped) {
      console.log(`  - ${name}: ${reason}`);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
