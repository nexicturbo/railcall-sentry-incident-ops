# QA evidence

Deterministic validation began at **2026-08-02T11:36:33Z**. Live Sentry validation
and marketplace publication followed on 2026-08-02. No credential, DSN, user PII,
or raw event payload is stored in this bundle.

## Deterministic validation

- `python -m unittest discover -s tests -q`: **91/91 passed**.
- `python -m compileall -q handlers sentry_incident_ops scripts tests`: passed.
- `python -m json.tool module.json`: passed.
- Python 3.9 grammar parse: **16/16 Python files passed**.
- README word count: **357**, below the 500-word contest ceiling.
- Trailing-whitespace scan: passed.

The tests cover all ten handlers, documented request paths and methods, query encoding,
cursor parsing, response bounds, token lookup/redaction (including a provider echo),
privacy views, input bounds, no-op idempotency, stale-approval refusal before PUT,
post-write verification, and deterministic proof chaining.

## Real Sentry API validation

A disposable Sentry organization project (`railcall-sentry-smoke`) received one
purpose-built error at **2026-08-02T18:38:44Z**, producing issue
`RAILCALL-SENTRY-SMOKE-1` (numeric ID `7648258921`). The temporary personal token had
only `event:read`, `event:write`, `member:read`, `org:read`, `project:read`, and
`team:read`; it remained outside the project and was never printed.

`scripts/live_smoke.py` exercised the same transport and privacy views used by the
module. Projects, teams, members, issues, issue detail, events, and tag values all
returned HTTP 200. The result contained one project, two privacy-minimized owners,
one issue, one event, and one safe tag value; raw event payloads and structured user
fields remained omitted.

The live write path then:

1. changed priority from `high` to `low` and verified the subsequent GET;
2. rejected a stale plan expecting `high` while Sentry reported `low`, before PUT;
3. restored priority from `low` to `high` and verified the subsequent GET; and
4. repeated the `high` target as an idempotent no-op with `changed: false`.

Both real writes returned HTTP 200 and emitted the four-phase `intent -> observed ->
decision -> verified` proof chain. The disposable issue finished in its original
`unresolved`, `high`, unassigned state.

## Official station compatibility

`scripts/station_compat.py` loaded the handlers through the capability gate from the
current official RailCall **station-v0.44** bundle. It registered **10/10 commands**,
reported network `['sentry.io']`, subprocess `false`, filesystem writes `[]`, and
blocked an undeclared `example.invalid` origin.

- Bundle SHA-256:
  `089fc94e62400bccb8a98cea3636691dccfef1be2c528cd9fa54fa29b897117a`
- Station build: `2026-07-31T01:16:06Z`
- Core commit: `dd7a93ad2172e6b8adb1304c3d1cedbdda10c4f1`

## Publisher signature

The module is signed with the local RailCall marketplace publisher identity whose
public Ed25519 key is
`4e92f188a4a3a6af1c517a712a6f81a9a2b4f2b4b7bf7978d7030d787e8af618`.
`railcall market module verify` accepted the v2 tree signature, confirmed ownership
by the local publisher key, and reported all ten commands across the 25-file signed
tree. The private seed is stored outside the project and is never included in this
evidence bundle.

## Source semantics checked

- Issue mutation uses official `PUT /api/0/organizations/{org}/issues/{issue}/`.
- Unassignment sends the empty string, matching Sentry's current endpoint tests.
- Mark-reviewed sends `inbox=false`, matching Sentry's current `update_inbox` source
  (`MARK_REVIEWED` transition), and verifies the subsequent GET.
- Event requests explicitly send `full=false`; retrieve-issue collapses release, stats,
  and tags before the privacy-minimized view is built.

## Reproducibility hash

Sorted relative path + tab + per-file SHA-256, newline-delimited, excluding
`QA_EVIDENCE.md`, the generated `module.sig`, `.reference/`, `__pycache__/`, and
`.pyc` files:

- 25 files
- tree-manifest SHA-256:
  `92441ebc5030aeb0cedcf0ba3491483f46579ba6487188ecee046f0bac6f846e`
- `module.json`: `82d731dcaa6c4613df08e8f4e9ff3c53039e5cccb258fe111ad38d182ab2eff3`
- `handlers/handler.py`: `d752e6a2489da3a2ff47fb5013bba5cf9ffc3f3e65d21ac74239e9779512617f`
- `sentry_incident_ops/domain.py`: `a0eb2633cd2e1f5bc26c91d5ca72971efdc25ea8b28620fce7ca25211ea1409c`
- `sentry_incident_ops/transport.py`: `0c62ede21baf0e29975c78df51b1f17a891792eff82d4bbefe414ab2ebbd6831`
- `sentry_incident_ops/proof.py`: `14b9ce2f02cadf021da7db0b02ee5989ede1ee34495520d4262e002299624c93`
- `README.md`: `39173694b5b05f87bc18014aa35c50d341e363127774a81ffe3b47a22e00ff15`
- `tests/test_manifest.py`: `1c3e44794bb64d1f7b8e6b165bc54f91c0f260df6682d1cd8136d0af5c64f424`

## Marketplace publication state

Version 0.1.0 entered RailCall's manual review queue at **2026-08-02T18:29:12Z** as
`nexicturbo/sentry-incident-ops`, free and tagged `contest:2026Q3`. Version 0.1.2 adds
the completed live evidence above. The listing is not described as contest-entered
or awarded until RailCall approves it and the marketplace URL is posted to the
Freelancer contest.
