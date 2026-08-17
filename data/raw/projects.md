---
source: projects.md
last_updated: 2026-06-28
document_type: guide
access_level: public
version: 1.8
---

# Projects

## Overview
Projects are the primary way to organize files and collaborate in AcmeCloud. Each project has its own membership, roles, and storage. Projects are separate from organization membership (see access-control.md).

## Creating a Project
1. From the Dashboard, select New Project.
2. Enter a project name and an optional description.
3. Select Create.

The user who creates a project becomes its Owner. Project names must be unique within the organization.

## Project Membership
Project Owners and organization administrators add members from the project's Members tab. Members must already be organization members. A user is granted access to a project's files only after being added to that project.

## Project Roles
- Owner — full control of the project, including deletion.
- Editor — can add and modify files and share them.
- Viewer — read-only access to project files.

Roles are assigned per project and do not affect other projects.

## Project Storage Limits
Each project draws from the organization's storage quota. Total storage is limited by the plan; see billing.md for per-plan quotas. The Dashboard shows per-project storage usage.

## Archiving and Deleting Projects
Archiving a project makes it read-only and hides it from the default view; it can be restored. Deleting a project moves its files to Trash for 30 days, after which they are permanently removed. Only Owners and administrators can archive or delete a project.
