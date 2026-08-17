---
source: account-recovery.md
last_updated: 2026-07-08
document_type: guide
access_level: public
version: 1.3
---

# Account Recovery

## Overview
Account recovery covers regaining access when you cannot sign in. There are three distinct procedures, and it is important to use the correct one:
- Password reset — you forgot your password but still control your email and MFA.
- MFA recovery — you lost your MFA device (see mfa.md).
- Account recovery — you lost access to both your email and MFA.

## Password Reset (Forgot Password)
1. Go to https://app.acmecloud.com.
2. Select "Forgot Password".
3. Enter your account email address.
4. Check your email for a reset link.
5. Open the link and set a new password.

The reset link is valid for 30 minutes. A password reset does not disable MFA and does not change any files, projects, or permissions.

## Account Recovery (Lost Email Access)
If you cannot access your account email, you cannot use the self-service password reset. Instead:
1. Contact your organization administrator.
2. The administrator verifies your identity out of band.
3. The administrator initiates recovery from the Admin Console.
4. You regain access with a temporary password that must be changed at the next sign-in.

This flow exists because self-service recovery relies on email verification.

## Locked Accounts
After 5 consecutive failed sign-in attempts, an account is locked for 15 minutes. The lock clears automatically. An administrator can unlock an account immediately from the Admin Console under Users.

## Admin Reset vs Self-Service Reset
Self-service password reset requires access to the account email. An administrator reset does not; it issues a temporary password. Administrators cannot recover or view a user's MFA codes — they can only reset MFA (see mfa.md).

## Frequently Asked Questions
- Does a password reset log me out everywhere? No; existing sessions are unaffected unless you sign out or an administrator revokes them.
- Does account recovery change my role or projects? No.
