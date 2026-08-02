# Marketplace listing draft

## Sentry Incident Operations Airlock

Give an AI incident responder six useful Sentry reads and four guarded issue actions
without handing it an unattended production write path.

Every status, owner, priority, or review mutation pauses at RailCall approval, fetches
the live issue immediately before execution, refuses stale state, verifies the result
after Sentry's PUT, and returns a deterministic proof chain inside the signed receipt.
Events are privacy-minimized; tokens live only in the vault; the sandbox allows only
`sentry.io`, with no subprocess or filesystem writes.

Built and tested against Sentry's official organization issue, event, tag, project,
team, member, and update APIs. Includes 91 deterministic contract tests plus a real
read-only smoke script and exact write-verification procedure.

Tags: `sentry`, `incident-response`, `observability`, `security`, `contest:2026Q3`
