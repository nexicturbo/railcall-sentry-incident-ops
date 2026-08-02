# Security model

## Trust boundaries

RailCall's signed Airlock receipt and approval bind the exact command payload. This
module treats Sentry, operator inputs, and API responses as untrusted. The Sentry
token is retrieved from RailCall's vault at execution time and is never accepted as
an action input.

## Enforced invariants

- The only origin is `https://sentry.io/api/0`; every path segment is URL-encoded.
- Manifest capabilities allow only `sentry.io`, no process creation, and no writes to
  the local filesystem.
- Requests and result counts are bounded. Responses above 4 MiB are refused.
- Errors expose an HTTP status and short provider message, but never request headers,
  bearer tokens, raw response objects, or URLs containing operator queries.
- Raw event bodies, structured user fields, request contexts, stack data, and
  non-allowlisted tags are discarded before returning a result. Sentry title/message
  text may still contain application data and must be scrubbed at SDK ingestion.
- Each write fetches live state after approval. A mismatch with any `expected_*`
  value refuses the operation before PUT.
- A write already at its target is a no-op. An actual PUT is followed by another GET;
  a mismatched outcome fails loudly instead of claiming success.
- The result includes a deterministic intent → observation → decision → verification
  SHA-256 chain, then RailCall seals the complete result in its signed receipt.

## Least privilege

Read commands need `org:read`, `project:read`, `team:read`, `member:read`, and
`event:read`. Write commands additionally need `event:write`. Do not grant
`project:admin`, `org:admin`, or billing scopes.

## Reporting

Do not include tokens, event payloads, or customer data in an issue. Report a
reproduction using fixture IDs and expected or observed behavior.
