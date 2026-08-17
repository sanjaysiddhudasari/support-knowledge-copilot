---
source: file-storage.md
last_updated: 2026-07-03
document_type: reference
access_level: public
version: 1.6
---

# File Storage

## Overview
AcmeCloud stores files within projects. This document covers upload limits, quotas, versioning, and retention.

## Uploading Files
Files can be uploaded through the web app (drag-and-drop or the Upload button) or via the API (POST /v1/files). See api.md for API details. All file types are supported.

## File Size Limits
The maximum upload size is 10 GB per file by default. Administrators can change this to any value between 1 GB and 50 GB using the max_file_size setting. Attempts to upload a file larger than the limit fail with error ACM-409. See security.md for the setting.

## Storage Quotas
Storage quotas are per plan:
- Free — 5 GB
- Pro — 100 GB
- Business — 1 TB
- Enterprise — unlimited (subject to fair use)

When the quota is reached, uploads are blocked until files are deleted or the plan is upgraded.

## File Versions
AcmeCloud keeps the last 10 versions of each file automatically. You can restore an earlier version from the file's version history. Older versions are discarded once a new version exceeds the 10-version limit.

## File Retention (Trash)
Deleted files move to Trash and are retained for 30 days. During this period they can be restored. After 30 days they are permanently deleted. Enterprise administrators can extend this period.

## Supported File Types
All file types are supported, including documents, images, video, and archives, up to the file size limit. Executable files can be stored but are flagged for administrators.
