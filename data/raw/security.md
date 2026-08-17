---
source: security.md
last_updated: 2026-07-22
document_type: policy
access_level: internal
version: 3.1
---

# Security

## Overview
This document describes the security settings administrators can configure and the security posture of AcmeCloud. Settings are managed from the Admin Console → Security.

## Session Security (session_timeout)
Administrators configure the session inactivity timeout with the session_timeout setting. The default is 30 minutes; valid values are between 15 and 120 minutes. Shorter timeouts are recommended for organizations with sensitive data.

## MFA Enforcement (require_mfa)
The require_mfa setting requires multi-factor authentication for all users. When enabled, unenrolled users have a 14-day grace period to enroll before sign-in is blocked. See mfa.md for enrollment instructions.

## File Size Policy (max_file_size)
The max_file_size setting controls the maximum upload size. The default is 10 GB; valid values are between 1 GB and 50 GB. See file-storage.md for how uploads behave at the limit.

## API Key Security (api_key_expiry)
The api_key_expiry setting controls API key expiration. The default is 90 days; valid values are between 30 and 180 days. Shorter expiration periods reduce the risk from leaked keys. See api.md.

## Data Encryption
AcmeCloud encrypts data at rest using AES-256 and in transit using TLS 1.3. Encryption is always enabled and cannot be disabled.

## Access Logging
AcmeCloud records sign-in events and administrative actions in an access log. Administrators can view the log from the Admin Console. Logs are retained for 1 year.

## Security Alerts
Security alerts notify users of sign-ins from new devices, password changes, and MFA changes. These alerts cannot be disabled (see notifications.md).
