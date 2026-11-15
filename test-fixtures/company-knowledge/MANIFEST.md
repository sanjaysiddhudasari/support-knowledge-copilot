# AcmeCloud — Live-Ingestion Test Fixtures

Synthetic, fictional test data for manually testing the Support Knowledge
Copilot upload -> ingest -> retrieve -> cite flow. **Nothing here is real
company policy.** AcmeCloud is the same fictional company the existing corpus
uses; these are new documents, not copies of it. Do not upload these to a
production knowledge base.

## Access-level note (important)

In this app, **access level is set via Markdown frontmatter only.** PDF, DOCX,
TXT, and HTML loaders have no content-based access control and **default to
`internal`**. So:

- The **public** and **admin** fixtures are **Markdown** files that carry the
  level in their frontmatter; they are the only two that will actually test
  public/admin filtering through the normal upload flow.
- The four non-Markdown files will ingest as `internal`, regardless of what
  the prose says. Do not assume their content sets an access level.

Status: **local only** (nothing uploaded).

| File | Format | Topic | Marker | Access | Suggested query | Facts to check appear |
|---|---|---|---|---|---|---|
| `acmecloud_travel_expenses.pdf` | PDF | Travel & expense reimbursement | `ACMECLOUD_TRAVEL_TEST_6K2Q` | internal | "How do I get travel reimbursed?" | Reimbursement within 10 business days; receipt required over $75; Concur; People Operations |
| `acmecloud_vendor_onboarding.docx` | DOCX | Vendor onboarding & invoice processing | `ACMECLOUD_VENDOR_TEST_7H3P` | internal | "How are vendor invoices paid?" | Net-30 terms; 2 business day processing; AP match within 5%; procurement@acmecloud.example |
| `acmecloud_laptop_provisioning.md` | Markdown | Laptop provisioning & return | `ACMECLOUD_LAPTOP_TEST_8J4R` | **public** | "How do I get a new laptop?" | 14"/16" models; encryption; return within 5 days; IT Operations |
| `acmecloud_incident_communications.txt` | TXT | Incident comms & status updates | `ACMECLOUD_INCIDENT_TEST_5K6S` | internal | "How often are SEV-1 updates posted?" | SEV-1 update every 30 min; notice within 15 min; postmortem in 5 business days |
| `acmecloud_change_management.md` | Markdown | Change-management approval | `ACMECLOUD_CHANGE_TEST_9L2T` | **admin** | "What is needed to approve a high-risk change?" | CAB + CTO sign-off; rollback plan; change freeze last two weeks of quarter |
| `acmecloud_support_handoff.html` | HTML | Escalation & support handoff | `ACMECLOUD_HANDOFF_TEST_3M8V` | internal | "When does L1 escalate to L2?" | Escalate after 1 business day; L2->L3 in 2 days; summary required in notes |

## Validation (already run)

All six files were generated, opened, and re-extracted with the app's own
loaders (`app.ingestion.loader.load_document`):
- Marker present and extractable in every file (PDF via pypdf, DOCX via
  python-docx, HTML as readable text, MD/TXT as text).
- Every file references **AcmeCloud** (consistent fictional company).
- PDF is a text-layer PDF, not a scan.
- DOCX headings and paragraphs present.
- HTML does not rely on scripts.
- Markers are unique across all six (0 cross-document leaks).
- Access levels parsed: `acmecloud_laptop_provisioning.md` -> public,
  `acmecloud_change_management.md` -> admin, all others -> internal.

## Manual upload instructions

1. Log in to the deployed app as an **admin**.
2. Sidebar -> **Upload document** -> pick each file (one at a time).
3. After each upload, it should appear in Supabase Storage (`documents`
   bucket) and Postgres (`documents` table), and the sidebar's
   **My Documents** list should show it.
4. Ask the suggested query for that file and confirm the answer cites that
   file's source.
5. **Access-control test:** log in as a **public** user and confirm
   `acmecloud_change_management.md` (admin) and the four internal files are
   **not** returned, while `acmecloud_laptop_provisioning.md` (public) is.
   Log in as an **admin** to verify the internal/admin files now appear.

Suggested format variety: PDF, DOCX, Markdown, TXT, HTML — exercises five
different parsers.

## Automating the upload (optional)

`_upload_fixtures.py` runs the real ingest pipeline from this machine against
your configured cloud Supabase + Qdrant (Storage, Postgres metadata, Qdrant
index, BM25 rebuild) and honours the parsed access level. It uses your `.env`.
Re-running is idempotent (same filename bumps version).

```bash
python test-fixtures/company-knowledge/_upload_fixtures.py
```

## Disclaimer
- Supabase and Qdrant were **not** modified by creating these files.
- The owner must upload them through the app (or run `_upload_fixtures.py`)
  to exercise a real integration.
- No credentials or secrets are baked into these fixtures.