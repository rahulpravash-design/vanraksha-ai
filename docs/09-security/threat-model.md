# Threat model (summary)

- **Auth**: bcrypt password hashing (72-byte limit enforced, not silently
  truncated), JWT with a minimum 32-byte signing key enforced at startup, and
  a production boot refusal if the key is still the shipped dev value or the
  database is still SQLite (`app/config.py: validate_for_runtime`).
- **Timing**: login compares against a dummy bcrypt hash when the user does
  not exist, so response timing does not distinguish "wrong password" from
  "no such account"; registration returns the same error shape for a
  duplicate email without echoing it back (full email-enumeration closure
  needs a confirm-by-email flow — not built here, tracked as a known gap).
- **Access control**: enforced at the query layer (`services/analytics.py:
  apply_scope`, `security.py: visible_scope`), not the presentation layer. A
  farmer requesting another farmer's report gets 404, not 403 — confirming a
  record exists is itself a disclosure.
- **Input validation**: Pydantic models reject cross-field nonsense (deaths >
  affected, affected > herd size, coordinates without their pair, dates more
  than an hour in the future) before anything reaches the database.
- **Audit trail**: every state-changing request writes an append-only
  `AuditLog` row with actor, role, action, and entity.
- **Known gaps**: no rate limiting yet, no CSRF consideration needed (bearer
  token, not cookie auth) but no refresh-token rotation either, and the
  email-enumeration timing fix above is partial. None of these block a demo;
  all of them block a production deployment.
