---
source: user-management.md
last_updated: 2026-07-05
document_type: guide
access_level: admin
version: 2.0
---

# User Management

## Overview
Organization administrators and owners manage user accounts from the Admin Console. This covers inviting users, assigning roles, disabling accounts, and resetting passwords.

## Inviting Users
1. Open the Admin Console and select Users.
2. Select Invite User.
3. Enter the new user's email address.
4. Choose a role (see User Roles).
5. Select Send Invite.

The invitee receives an email with a link to set up their account. Invitations expire after 7 days if not accepted.

## User Roles
Every user has one organization role:
- Owner — full access, including billing and deleting the organization.
- Admin — manages users, security settings, and all projects.
- Member — creates projects, uploads files, and shares content.
- Viewer — read-only access to the projects they are added to.

See access-control.md for the complete permission matrix.

## Disabling vs Deleting Users
Disabling a user blocks sign-in immediately but preserves their files and history. Deleting a user removes the account and transfers ownership of their files to an administrator (required before deletion). Prefer disabling over deleting when an employee leaves temporarily.

## Resetting a User's Password
Administrators reset passwords from Users → (user) → Reset Password. This issues a temporary password that must be changed at the next sign-in. Resetting a password does not reset the user's MFA.

## User Status
A user's status is one of: active, invited (not yet accepted), or suspended. Suspended users cannot sign in and appear grayed out in member lists. Suspension is reversible; deletion is permanent.

## Bulk Operations
Administrators can invite multiple users at once by uploading a CSV with email and role columns. Bulk invitations are processed asynchronously; each row that fails is reported with a reason.
