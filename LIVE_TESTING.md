# Real Sentry API validation

The deterministic suite uses contract fixtures so it is safe in CI. Before publishing,
run this separate smoke test against a free Sentry developer organization. The script
uses the same `SentryClient`, documented endpoints, bearer header, validators, and
privacy views as the RailCall handlers. It never prints the token.

## 1. Create least-privilege credentials

Create an organization auth token in Sentry with:

- read-only smoke: `org:read`, `project:read`, `team:read`, `member:read`, `event:read`
- handler write verification: additionally `event:write`

Create a disposable project and send at least one test error. Record the organization
slug and resulting numeric issue ID.

## 2. Run the read-only live smoke

PowerShell:

```powershell
$env:SENTRY_AUTH_TOKEN = '<temporary token>'
$env:SENTRY_ORG = '<organization slug>'
$env:SENTRY_ISSUE_ID = '<issue id>'
python scripts/live_smoke.py
Remove-Item Env:SENTRY_AUTH_TOKEN
```

The script checks all six read actions against `https://sentry.io/api/0`, prints only
counts, IDs, status codes, and privacy-minimized views, and exits nonzero on any
fabricated or malformed response.

## 3. Verify writes through RailCall

Install and sign the module through RailCall's publisher flow, save the token in the
Sentry vault integration, and use only the disposable issue:

1. Read it with `sentry.get_issue` and copy the current status, assignee, priority,
   and `inbox` values.
2. Stage each write with those values as the `expected_*` fields.
3. Before approving one staged action, change the same field in Sentry. Approval must
   fail with `stale approval` and make no `PUT`.
4. Restage with the new live value; approve and verify the receipt's `before`, `after`,
   `changed`, and four-phase `safety_proof`.
5. Repeat an already-completed target. It must return `changed: false` after one GET
   and no PUT.

`mark_issue_reviewed` sends `inbox=false`, which current Sentry source maps to its
`MARK_REVIEWED` transition. Use a disposable issue because the action can also move
an unresolved substatus to ongoing.

Authoritative API references:

- https://docs.sentry.io/api/events/list-an-organizations-issues/
- https://docs.sentry.io/api/events/retrieve-an-issue/
- https://docs.sentry.io/api/events/update-an-issue/
- https://docs.sentry.io/api/events/list-an-issues-events/
- https://docs.sentry.io/api/events/list-a-tags-values-for-an-issue/
- https://docs.sentry.io/api/organizations/list-an-organizations-projects/
- https://docs.sentry.io/api/teams/list-an-organizations-teams/
- https://docs.sentry.io/api/organizations/list-an-organizations-members/
- https://github.com/getsentry/sentry/blob/master/src/sentry/issues/update_inbox.py
