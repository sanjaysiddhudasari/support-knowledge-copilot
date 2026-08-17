---
source: troubleshooting.md
last_updated: 2026-07-20
document_type: troubleshooting
access_level: public
version: 2.6
---

# Troubleshooting

## Overview
This guide explains common AcmeCloud error codes and how to resolve them. Error codes appear in the web app and in API responses.

## ACM-401 — Authentication Failed
This error means the supplied credentials are invalid or the session/API token has expired. Verify your email and password. If you use an API key, confirm the key has not expired (see api.md). For web sign-in, try the Forgot Password flow.

## ACM-403 — Forbidden
You are authenticated but do not have permission for the requested action. Check your role (see access-control.md). Contact a project Owner or an administrator if you believe the permission is wrong.

## ACM-404 — Not Found
The requested resource does not exist or has been deleted. For files, check that the file was not moved to Trash. For share links, the link may have been revoked or expired.

## ACM-409 — Conflict
The request conflicts with existing state. Common causes: a duplicate project name, or an upload exceeding the max_file_size limit. Rename the resource or reduce the file size and retry.

## ACM-429 — Rate Limit Exceeded
This error means the API rate limit has been exceeded. The default limit is 1,000 requests per minute per API key. Wait for the interval indicated in the Retry-After header and retry, or request a higher limit (Enterprise).

## ACM-500 — Internal Server Error
An unexpected server error occurred. This is not caused by your request. Retry after a short delay; if the error persists, contact support with the request ID shown in the error.

## Common Login Issues
- "Invalid credentials" — check Caps Lock and the correct email address.
- Account locked — wait 15 minutes or ask an administrator to unlock the account.
- MFA code rejected — check the device clock and try a backup code.

## Upload Failures
Uploads can fail for these reasons: the file exceeds max_file_size, the storage quota is full, or the network connection dropped. Check the file size, free up storage, and retry.
