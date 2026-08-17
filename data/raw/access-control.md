---
source: access-control.md
last_updated: 2026-07-12
document_type: reference
access_level: internal
version: 2.2
---

# Access Control

## Overview
Access control in AcmeCloud determines what a user can see and do. It is built on two concepts: authentication (proving who you are) and authorization (what you are allowed to do). This document describes authorization.

## Authentication vs Authorization
Authentication verifies your identity at sign-in (email, password, and MFA). Authorization determines which resources you can access and what actions you can perform once signed in. A user can be authenticated yet denied access to a resource if they lack permission.

## Organization Roles
Organization roles apply across the whole workspace:

| Role | Manage users | Manage billing | Create projects | Edit content |
|------|-------------|----------------|-----------------|--------------|
| Owner | Yes | Yes | Yes | Yes |
| Admin | Yes | No | Yes | Yes |
| Member | No | No | Yes | Yes |
| Viewer | No | No | No | No |

## Project Membership vs Organization Membership
Organization membership means a user has an account in the workspace. Project membership is separate: a user must be added to a project to access its files. Being an organization member does not grant access to any project automatically.

## File Owner vs File Editor
Within a file or project, a user can be:
- Owner — can delete, change permissions, and share.
- Editor — can modify content but not delete or change permissions.
- Viewer — can read but not modify.

Only the file owner (or an administrator) can transfer ownership.

## Project Roles
Each project has its own roles: Owner, Editor, and Viewer. Project roles are independent of organization roles. For example, a Member (organization role) added to a project as Viewer cannot edit project files.

## Changing Permissions
Administrators and resource owners can change permissions from the sharing dialog or the project settings. Permission changes take effect immediately and apply to existing sessions.
