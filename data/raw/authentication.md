---
source: authentication.md
last_updated: 2026-07-16
document_type: guide
access_level: public
version: 3.3
---

# Authentication

## Overview
AcmeCloud authenticates users with an email address and password at the sign-in page (https://app.acmecloud.com). After a successful sign-in, AcmeCloud issues a session token that identifies the user for the duration of the session. Session tokens are separate from API keys; see api.md for how programmatic access authenticates.

## Signing In
1. Go to https://app.acmecloud.com.
2. Enter the email address associated with your AcmeCloud account.
3. Enter your password.
4. If multi-factor authentication (MFA) is enabled, enter the six-digit code from your authenticator app.
5. Select Sign In.

If sign-in fails, verify that Caps Lock is off and that you are using the same email address your administrator used to invite you.

## Session Timeout
Sessions expire after 30 minutes of inactivity by default. When a session expires, you are returned to the sign-in page and must sign in again. Organizations can adjust this value using the session_timeout setting described in security.md.

## Signing Out
Select your profile icon in the top-right corner, then choose Sign Out. Signing out invalidates the current session token immediately. Closing the browser tab does not sign you out; the session remains valid until the inactivity timeout is reached.

## Single Sign-On (SSO)
Organizations on the Enterprise plan can enable SAML single sign-on so users sign in through the organization's identity provider instead of an AcmeCloud password. When SSO is enabled, users sign in at the organization-specific SSO URL. An administrator can disable password-based sign-in entirely.

## Account Lockout
To protect accounts, AcmeCloud locks an account for 15 minutes after 5 consecutive failed sign-in attempts. During the lockout, sign-in is blocked even with the correct password. The lock clears automatically after 15 minutes; an organization administrator can unlock an account earlier from the Admin Console. See account-recovery.md for details.

## Troubleshooting Sign-In
- Error ACM-401 ("invalid credentials") usually means the email or password is incorrect, or the session token has expired.
- If your account is locked, wait for the lockout to expire or ask an administrator to unlock it.
- If you forgot your password, use the Forgot Password flow described in account-recovery.md.
