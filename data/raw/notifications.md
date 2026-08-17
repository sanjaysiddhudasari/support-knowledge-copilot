---
source: notifications.md
last_updated: 2026-07-09
document_type: guide
access_level: public
version: 1.2
---

# Notifications

## Overview
AcmeCloud sends email notifications for account and workspace activity. Users control which non-security notifications they receive from Notification Settings.

## Notification Types
- Project updates — new members, role changes, project archiving.
- File changes — uploads, edits, deletions, new share links.
- Security alerts — sign-ins from new devices, password changes, MFA changes.
- Billing — invoices, payment failures, plan changes.
- Digests — daily or weekly summaries of activity.

## Email Preferences
Open Notification Settings to enable or disable each non-security type. Preferences apply per user and take effect immediately.

## Digest Settings
Instead of individual file-change emails, you can receive a daily or weekly digest using the notification_digest setting. The digest summarizes activity in one email. Choose "None" to receive individual notifications instead.

## Security Alerts vs Notification Emails
Security alerts are separate from regular notification emails and cannot be disabled. Regular notifications (for example, file-change emails) can be disabled by the user; security alerts always send.

## Muting Notifications
You can mute notifications for a specific project from the project's notification settings. Muting a project suppresses project-update and file-change emails for that project only; security alerts are unaffected.
