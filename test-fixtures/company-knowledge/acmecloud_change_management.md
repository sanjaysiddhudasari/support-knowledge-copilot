---
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
