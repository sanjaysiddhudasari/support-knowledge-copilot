---
source: file-sharing.md
last_updated: 2026-07-14
document_type: guide
access_level: public
version: 2.4
---

# File Sharing

## Overview
Files can be shared in two ways: by adding users to a project (direct access) or by creating a share link. This document covers share links. See access-control.md for direct project access.

## Creating a Share Link
1. Open the file and select Share.
2. Choose the link permission: View (read-only) or Edit.
3. Set an expiration (optional) and a password (optional).
4. Select Create Link, then copy the URL.

Anyone with the link can access the file according to the link permission, even if they are not an AcmeCloud user.

## Link Permissions
- View — the recipient can open and download the file but cannot modify it.
- Edit — the recipient can modify the file. Edit links require the recipient to sign in to AcmeCloud.

## Link Expiration
Share links expire after 7 days by default. You can set an expiration up to 90 days, or choose "Never" for links that should not expire. An expired link can be re-enabled only by creating a new link.

## Link Passwords
You can optionally protect a share link with a password. Recipients must enter the password before viewing the file. Passwords apply to both View and Edit links.

## Expired Links
When a recipient opens an expired link, they see a message that the link has expired and are told to contact the file owner for a new link. The file itself is not deleted.

## Share Link vs Direct Access
A share link grants access to a single file with the chosen permission. Direct project access grants access to all files in a project according to the user's project role. Revoking a project role does not revoke existing share links.
