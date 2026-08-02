# Sentry Incident Operations Airlock

An agent resolving the wrong Sentry issue can hide the incident responders still
need. This module gives an AI operator the context to triage incidents while every
mutation stops for human approval, rechecks live state, and leaves a signed receipt.
It is built for small engineering teams that want useful incident automation without
an unattended production write path.

## Install

```bash
railcall market install nexicturbo/sentry-incident-ops
```

In RailCall Studio, open **Integrations → Sentry (from module
nexicturbo/sentry-incident-ops)** and save a Sentry organization auth token as
`SENTRY_AUTH_TOKEN`. (The separate built-in Sentry card is not this module.) Use only
these scopes:

- reads: `org:read`, `project:read`, `team:read`, `member:read`, `event:read`
- writes: add `event:write`

No organization slug, issue ID, or token is stored by the module.

## Commands

Reads: `list_projects`, `list_owners`, `list_issues`, `get_issue`,
`list_issue_events`, `list_issue_tag_values`.

Approved writes: `set_issue_status`, `assign_issue`, `set_issue_priority`,
`mark_issue_reviewed`.

## Example

Find active checkout failures:

```json
{"command_id":"sentry.list_issues","inputs":{"organization_slug":"acme","query":"is:unresolved checkout","stats_period":"24h","limit":20}}
```

Then stage a guarded resolution:

```json
{"command_id":"sentry.set_issue_status","inputs":{"organization_slug":"acme","issue_id":"42","expected_status":"unresolved","status":"resolved"}}
```

**Expected:** RailCall shows the exact intent for approval. After approval, the
handler fetches issue `42`. If its status is no longer `unresolved`, it refuses the
stale approval without writing. Otherwise it sends one Sentry `PUT`, reads the issue
again, verifies `resolved`, and returns a deterministic safety proof inside
RailCall's signed receipt.

## Safety and evidence

- Token: vault only; never an input, log field, output, or error.
- Capability sandbox: HTTPS only to `sentry.io`; no subprocess or file writes.
- All inputs are bounded; path components are encoded; responses are capped at 4 MiB.
- Event output omits raw payloads, users, contexts, and non-allowlisted tags.
- Mutations are idempotent, preconditioned, and verified after execution.
- Sentry HTTP errors and `429` retry timing are surfaced; success is never invented.
- 91 deterministic contract tests cover validation, privacy, transport, stale-state
  refusal, no-op behavior, writes, and proof chains. See `LIVE_TESTING.md` for real API
  validation.
- A disposable live Sentry run on 2026-08-02 exercised all six reads, one verified
  priority write, stale-approval refusal, restoration, and an idempotent no-op.

## Limits

Only issue triage is in scope. It does not expose event bodies, user PII, releases,
alerts, billing, or project administration. Safe tag values are limited to
`environment`, `release`, `level`, `transaction`, `handled`, and `mechanism`.
A read-only token runs reads; Sentry honestly refuses writes.

MIT · `contest:2026Q3`
