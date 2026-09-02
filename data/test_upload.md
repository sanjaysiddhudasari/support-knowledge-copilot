# API Key Management

AcmeCloud API keys allow applications to authenticate with the AcmeCloud API.

## Creating an API Key

Administrators can create a new API key from the API Settings page.

To create a key, open API Settings, select Create API Key, provide a descriptive name, and select Create.

The generated API key is displayed only once.

## API Key Expiration

API keys expire after 90 days by default.

Administrators can configure a different expiration period when creating an API key.

Expired API keys cannot be used to authenticate API requests.

## Revoking an API Key

Administrators can revoke an API key from the API Settings page.

After an API key is revoked, applications using that key will receive an authentication error.

Revocation takes effect immediately.

## API Key Security

API keys must be stored securely and must never be committed to source control.

Do not include API keys in publicly accessible code, documentation, or client-side applications.

If an API key is accidentally exposed, revoke it immediately and create a replacement key.