---
source: password-policy.md
last_updated: 2026-08-01
document_type: policy
access_level: internal
version: 2.1
---

# Password Policy

## Overview
This policy defines the password requirements enforced for all AcmeCloud user accounts in the organization. It applies to passwords set through the web app and the API. Individual users cannot opt out of these requirements.

## Password Requirements
All passwords must:
- Be at least 12 characters long.
- Contain at least one uppercase letter (A–Z).
- Contain at least one lowercase letter (a–z).
- Contain at least one number (0–9).
- Contain at least one special character (for example !, @, #, or %).

Passwords longer than 12 characters are encouraged but not required.

## Password Expiration
Passwords expire every 90 days by default. When a password expires, the user is prompted to set a new password at the next sign-in. Administrators can change the expiration period to any value between 30 and 180 days using the password_expiry setting. See security.md for configuration details.

## Password History
AcmeCloud prevents reuse of the last 5 passwords. When setting a new password, the new password must differ from each of the previous 5 passwords.

## Changing Your Password
1. Sign in to AcmeCloud.
2. Open Account Settings.
3. Select Security, then Change Password.
4. Enter your current password, then the new password twice.
5. Select Save.

The new password must satisfy the requirements above.

## Admin Password Management
Organization administrators can reset a user's password from the Admin Console under Users. Administrator resets generate a temporary password that the user must change at the next sign-in. Administrators cannot view existing user passwords.

## Policy Configuration
Administrators can configure password_expiry (30–180 days, default 90). The minimum length (12 characters) and the complexity rules are fixed by this policy and cannot be lowered.
