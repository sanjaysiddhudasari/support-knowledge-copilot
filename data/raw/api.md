---
source: api.md
last_updated: 2026-07-18
document_type: api
access_level: internal
version: 3.3
---

# AcmeCloud API

## Overview
The AcmeCloud REST API provides programmatic access to projects, files, and users. The base URL is https://api.acmecloud.com. All requests use HTTPS.

## Authentication
The API accepts two credential types:
- API keys — for server-to-server and long-running automation. Sent as a Bearer token.
- Session tokens — obtained by exchanging user credentials via POST /v1/auth/token.

API keys and session tokens are distinct; see API Key Management below.

## Obtaining a Session Token
```
POST /v1/auth/token
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "••••••••••••"
}
```
The response contains an access token that remains valid until the session inactivity timeout is reached.

## API Key Management
Create API keys from Account Settings → API Keys. Each key has a name, a scoped permission level, and an expiration. The full key value is shown only once at creation; store it securely. Keys use the prefix acm_.

## API Key Expiration
API keys expire after 90 days by default. Administrators can configure the expiration period to any value between 30 and 180 days using the api_key_expiry setting. When a key expires, requests fail with ACM-401. See security.md and release-notes.md for the history of this behavior.

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/auth/token | Exchange credentials for a session token |
| GET | /v1/projects | List projects |
| POST | /v1/projects | Create a project |
| POST | /v1/files | Upload a file |
| GET | /v1/files/{file_id} | Get file metadata |
| GET | /v1/files/{file_id}/download | Download a file |
| GET | /v1/users | List users |
| POST | /v1/users | Create a user |

## Rate Limits
The standard rate limit is 1,000 requests per minute per API key. Enterprise organizations can request higher limits. When the limit is exceeded, the API returns ACM-429 with a Retry-After header indicating when to retry.

## Error Codes
| Code | Meaning |
|------|---------|
| ACM-401 | Authentication failed (invalid or expired credentials) |
| ACM-403 | Forbidden (insufficient permissions) |
| ACM-404 | Resource not found |
| ACM-409 | Conflict (duplicate name, upload exceeds size limit) |
| ACM-429 | Rate limit exceeded |
| ACM-500 | Internal server error |

## Best Practices
Rotate API keys regularly, use the minimum required permission scope, and never embed keys in client-side code. Monitor the Retry-After header on ACM-429 responses.
