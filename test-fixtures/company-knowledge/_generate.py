"""Generate 6 realistic synthetic AcmeCloud knowledge documents.

Formats map to these topics so the owner can exercise different parsers.
Non-Markdown formats default to "internal" in this app (no content-based
access control); only the two Markdown fixtures carry a frontmatter access
level so public/admin access can actually be tested via the normal upload flow.

Run:  python test-fixtures/company-knowledge/_generate.py
"""

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
repo = OUT.parents[1]
sys.path.insert(0, str(repo / "tests" / "ingestion"))

from pdf_factory import write_pdf, write_docx  # noqa: E402

DISCLAIMER = (
    "Synthetic test content \u2014 AcmeCloud is fictional. "
    "Do not treat these procedures as real company policy."
)

TRAVEL_PDF = f"""{DISCLAIMER}

ACMECLOUD_TRAVEL_TEST_6K2Q

Travel and Expense Reimbursement

Purpose
This article explains how AcmeCloud employees book work travel and
claim expense reimbursements.

Scope
Applies to all full-time employees booking travel for AcmeCloud business
purposes. Does not apply to local commuting or client-reimbursed travel.

Owner
People Operations, travel desk at travel@acmecloud.example (fictional).

Last reviewed
2026-10-02.

Booking travel
1. Obtain manager approval by opening a Travel Request in Springboard before
   booking.
2. Book flights and hotels through the Concur platform using the corporate
   card. Do not book personal upgrades without approval.
3. Choose economy flights unless the route exceeds six hours, in which case
   premium economy is allowed.
4. Save the email confirmation to the request for audit.

Per-diem and expenses
Reimbursable: meals not provided by the event, ground transport, working
internet, and baggage fees. Not reimbursable: personal entertainment,
alcohol over 50 USD daily, and costs for family members.

Submit an expense report in Concur within 15 days of the return date. Attach
a receipt for any single expense over 75 USD; below that, a line-item
description is acceptable. Accounts Payable targets reimbursement within 10
business days after approval.

Exceptions and escalation
If travel must be approved outside business hours, contact the on-call travel
coordinator. Expense reports older than 45 days require finance director
approval before payment.

FAQ
- What is the travel expense marker to verify indexing?
  ACMECLOUD_TRAVEL_TEST_6K2Q appears in this article's introduction.
- Reimbursement is credited to the employee's default bank account on file,
  with a notification from the payroll system.
"""

VENDOR_DOCX = [
    ("heading1", "Vendor Onboarding and Invoice Processing"),
    ("paragraph", DISCLAIMER),
    ("paragraph", "ACMECLOUD_VENDOR_TEST_7H3P"),
    ("heading2", "Purpose and scope"),
    ("paragraph", (
        "This article explains how AcmeCloud onboards external vendors "
        "and processes their invoices. It applies to every supplier providing "
        "goods or services in a AcmeCloud production environment. The owner is "
        "Procurement, mailbox procurement@acmecloud.example (fictional)."
    )),
    ("heading2", "Onboarding steps"),
    ("paragraph", (
        "1. Submit a Vendor Intake form with the legal entity, tax ID, and "
        "services. 2. Complete the third-party risk questionnaire. 3. Collect "
        "and verify the W-9 and bank details (EFT form). 4. Obtain security "
        "review for vendors handling production data. 5. Route the agreement "
        "through legal; standard terms are Net-30."
    )),
    ("heading2", "Invoice processing"),
    ("paragraph", (
        "Vendors send invoices to ap@acmecloud.example (fictional) with a PO "
        "number in the subject. Accounts Payable matches the invoice to the PO "
        "and receipts. A match within 5 percent is auto-approved; anything "
        "larger goes to the budget owner. The payment SLA is 30 days from the "
        "invoice date, and the target processing time is 2 business days."
    )),
    ("heading2", "Escalation and exceptions"),
    ("paragraph", (
        "Failed matches, missing POs, or duplicate invoices escalate to the "
        "vendor manager. Any invoice without a valid PO is held and the vendor "
        "is notified within 5 business days."
    )),
    ("heading2", "FAQ"),
    ("paragraph", (
        "What is the vendor marker to verify indexing? "
        "ACMECLOUD_VENDOR_TEST_7H3P appears in the introduction. "
        "All vendor data is stored in the procure-to-pay system and never in "
        "email archives."
    )),
]

LAPTOP_MD = """---
access_level: public
document_type: guide
last_updated: 2026-10-02
---

# Laptop Provisioning and Equipment Return

{disclaimer_text}
ACMECLOUD_LAPTOP_TEST_8J4R

## Purpose and scope
This public article explains how new AcmeCloud employees receive a
managed laptop and how returning employees hand equipment back. It is owned
by IT Operations (helpdesk@acmecloud.example, fictional).

## Provisioning a new laptop
1. The People team opens an onboarding ticket in Atlas 5 business days before
   the start date.
2. IT selects the standard 14-inch model, or the 16-inch model for engineers
   and designers.
3. The device is imaged with the corporate image, disk encryption enabled,
   and joined to the domain.
4. The employee picks up the device from the office or it is shipped to the
   home address on file.
5. First sign-in uses single sign-on; the employee is prompted to set up
   two-factor at first login.

**Marker detail:** ACMECLOUD_LAPTOP_TEST_8J4R also appears in the FAQ below
so it can be retrieved independently of the title.

## Return process
Employees separating from the company must return the laptop within 5
calendar days of the last working day. Wipe personal files only; do not
remove the managed encryption or domain join. Return the charger and any
docking station. Damaged or lost equipment is reported through the same
onboarding ticket.

## Exceptions and escalation
Equipment that must ship internationally goes through IT Logistics with a
prepaid label. A returning employee without the device for more than 7 days
escalates to IT management.

## FAQ
- Where does the laptop marker appear? ACMECLOUD_LAPTOP_TEST_8J4R appears in
  the Purpose section and this FAQ.
- Remote-only employees receive the device by courier and confirm receipt in
  the same ticket.
""".replace("{disclaimer_text}", "Synthetic test content \u2014 AcmeCloud is fictional. Do not treat these procedures as real company policy.")

INCIDENT_TXT = f"""{DISCLAIMER}

ACMECLOUD_INCIDENT_TEST_5K6S

Incident Communications and Customer Status Updates

Purpose
Explains how AcmeCloud notifies customers and internal teams during
service incidents.

Scope
Applies to any incident that affects production availability or customer
data. Owner is the Incident Manager rotation, idm@acmecloud.example
(fictional). Last reviewed 2026-10-02.

Severity definitions
SEV-1: total service outage or a data integrity issue affecting many
customers. SEV-2: degraded service for a subset of customers. SEV-3: minor
functional issue with a workaround.

Communication cadence
SEV-1 incidents require a public status update every 30 minutes and a
customer-facing notice from the support team within 15 minutes of
declaration. SEV-2 updates post every 60 minutes. SEV-3 updates post once a
day or when resolved.

Customer reporting
Customer-facing status updates are drafted by the Incident Manager and
published to the status page. Named CSMs notify top accounts directly.
Internal chat must never contradict the published status; all updates cite
the incident marker ACMECLOUD_INCIDENT_TEST_5K6S so teams can correlate.

Resolution
An incident is closed when monitoring is stable for 2 consecutive hours.
Postmortem (5 whys) is required for every SEV-1 within 5 business days.

Escalation
If an incident is not resolved within 4 hours at SEV-1, it escalates to the
VP of Engineering. Do not wait for a customer to report; open the incident on
first reliable signal.
"""

CHANGE_MD = """---
access_level: admin
document_type: guide
last_updated: 2026-10-02
---

# Change-Management Approval Checklist

{disclaimer_text}
ACMECLOUD_CHANGE_TEST_9L2T

## Purpose and scope
This admin article defines the approval checklist all production changes must
pass at AcmeCloud. It applies to infrastructure, application, and
database changes touching the production environment. Owner is the Change
Advisory Board (CAB).

## Risk levels
- Low risk: reversible and isolated; example config toggle.
- Medium risk: moderate blast radius; example feature flag rollout.
- High risk: customer-impacting or irreversible; example schema migration.

## Approval matrix
- Low risk changes require the change owner's manager sign-off only.
- Medium risk changes require CAB approval at the weekly board.
- High risk changes require CAB approval and the CTO's explicit sign-off.

## Required checklist (all levels)
Each change request in Atlas must include: a change description, a
rollback plan, the affected systems, the planned window, and the test
results. The checklist is incomplete unless every field is filled. The
change marker ACMECLOUD_CHANGE_TEST_9L2T must be quoted in the request so
it can be tracked for indexing verification.

## Change freeze
A production change freeze applies for the last two weeks of each quarter.
Only emergency fixes approved by the CTO proceed during a freeze.

## Exceptions and escalation
Emergency changes bypass the normal window but must be logged within 24
hours and reviewed at the next CAB meeting.

## FAQ
- Where does the change marker appear? ACMECLOUD_CHANGE_TEST_9L2T appears in
  the checklist section above.
- A failed rollback is a new incident; open an incident and notify the CAB.
"""

HANDOFF_HTML = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Service-Level Escalation</title></head>
<body>
<h1>Service-Level Escalation and Support Handoff</h1>
<p>{DISCLAIMER}</p>
<p>ACMECLOUD_HANDOFF_TEST_3M8V</p>
<h2>Purpose and scope</h2>
<p>Explains how AcmeCloud escalates tickets and hands work between
support levels. Owner is Support Operations
(supportops@acmecloud.example, fictional). Last reviewed 2026-10-02.</p>
<h2>Support levels</h2>
<ul>
<li><b>L1:</b> triage, known solutions, password resets.</li>
<li><b>L2:</b> product configuration and reproducible bugs.</li>
<li><b>L3:</b> engineering deep-dives and code-level fixes.</li>
</ul>
<h2>Escalation criteria</h2>
<p>L1 escalates to L2 when a ticket is unresolved for 1 business day or the
issue reproduces on a clean environment. L2 escalates to L3 when a bug
requires source access or the resolution would change documented behavior.</p>
<h2>Handoff requirements</h2>
<p>A handoff is only accepted when the ticket notes include a summary, the
steps already tried, logs or reproduction steps, and the customer impact.
Escalation targets: L1 to L2 within 1 business day; L2 to L3 within 2
business days; SEV-1 tickets escalate immediately to the Incident Manager.</p>
<p>Handoff marker detail: ACMECLOUD_HANDOFF_TEST_3M8V must be present in
the summary so the ticket can be located for indexing checks.</p>
<h2>FAQ</h2>
<p>Q: Where does the handoff marker appear? A: In the introduction and in the
handoff requirements above.</p>
</body></html>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # PDF writer is latin-1; coerce any non-latin-1 char (e.g. em-dash) to a
    # harmless placeholder so generation never fails on unicode.
    pdf_text = TRAVEL_PDF.encode("latin-1", "replace").decode("latin-1")
    write_pdf(OUT / "acmecloud_travel_expenses.pdf", [pdf_text])
    write_docx(OUT / "acmecloud_vendor_onboarding.docx", VENDOR_DOCX)
    (OUT / "acmecloud_laptop_provisioning.md").write_text(LAPTOP_MD, encoding="utf-8")
    (OUT / "acmecloud_incident_communications.txt").write_text(INCIDENT_TXT, encoding="utf-8")
    (OUT / "acmecloud_change_management.md").write_text(CHANGE_MD, encoding="utf-8")
    (OUT / "acmecloud_support_handoff.html").write_text(HANDOFF_HTML, encoding="utf-8")

    for path in sorted(OUT.glob("acmecloud_*")):
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")

    print("generated", len(list(OUT.glob("acmecloud_*"))), "fixtures")


if __name__ == "__main__":
    main()