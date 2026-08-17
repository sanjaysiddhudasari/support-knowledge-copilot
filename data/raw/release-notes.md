---
source: release-notes.md
last_updated: 2026-07-15
document_type: release-notes
access_level: public
version: 3.3
---

# Release Notes

## Overview
This document summarizes changes across AcmeCloud releases. Entries are listed newest first. Historical entries may describe behavior that has since changed; refer to the current version of the relevant guide for present-day behavior.

## Version 3.3 — 2026-07-15
- API keys now support configurable expiration via api_key_expiry (30–180 days, default 90). Previously, API keys expired after a fixed 90 days.
- session_timeout is now administrator-configurable (15–120 minutes, default 30).
- Standard API rate limit raised to 1,000 requests per minute per key.
- Single sign-on (SAML) added for Enterprise organizations.

## Version 3.2 — 2026-05-20
- Added MFA backup codes (10 single-use codes).
- Added the require_mfa organization setting with a 14-day grace period.
- Added notification_digest (daily or weekly summaries).
- Deleted files are now retained in Trash for 30 days.

## Version 3.1 — 2026-02-14
- Password policy strengthened: minimum length increased from 8 to 12 characters, and complexity requirements (uppercase, lowercase, number, special character) were added.
- Maximum file size increased from 5 GB to 10 GB.
- Share-link expiration was introduced.
- File versioning was introduced (last 10 versions retained).

## Version 3.0 — 2025-11-10
- Initial release of AcmeCloud, including projects, file storage, user management, and the REST API.
- Initial limits: minimum password length 8 characters; API keys expired after a fixed 90 days; maximum file size 5 GB.

## Deprecations
No features are deprecated as of version 3.3.
