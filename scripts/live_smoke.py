#!/usr/bin/env python3
"""Read-only smoke test against real Sentry APIs; never prints the token."""

from __future__ import annotations

import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentry_incident_ops import domain  # noqa: E402
from sentry_incident_ops.transport import SentryClient  # noqa: E402


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def _list(response, label: str):
    if response.status != 200 or not isinstance(response.data, list):
        raise RuntimeError(f"{label}: expected HTTP 200 list")
    return response.data


def main() -> int:
    token = _required_env("SENTRY_AUTH_TOKEN")
    org = _required_env("SENTRY_ORG")
    requested_issue = os.environ.get("SENTRY_ISSUE_ID", "").strip()
    client = SentryClient(token)

    projects_plan = domain.plan_list_projects({"organization_slug": org, "per_page": 25})
    projects_response = client.list_projects(projects_plan)
    projects = [domain.project_view(item) for item in _list(projects_response, "projects")]

    owners_plan = domain.plan_list_owners({"organization_slug": org, "per_page": 25})
    teams_response = client.list_teams(owners_plan)
    members_response = client.list_members(owners_plan)
    owners = domain.owners_view(
        _list(teams_response, "teams"), _list(members_response, "members")
    )

    issues_plan = domain.plan_list_issues(
        {"organization_slug": org, "query": "is:unresolved", "limit": 10}
    )
    issues_response = client.list_issues(issues_plan)
    issues_raw = _list(issues_response, "issues")
    issues = [domain.issue_view(item) for item in issues_raw]
    issue = requested_issue or (issues[0]["id"] if issues else "")
    if not issue:
        raise RuntimeError("no unresolved issue found; set SENTRY_ISSUE_ID to a disposable issue")

    issue_plan = domain.plan_get_issue({"organization_slug": org, "issue_id": issue})
    issue_response = client.get_issue(issue_plan)
    if issue_response.status != 200 or not isinstance(issue_response.data, dict):
        raise RuntimeError("issue: expected HTTP 200 object")
    issue_view = domain.issue_view(issue_response.data)

    events_plan = domain.plan_list_issue_events(
        {"organization_slug": org, "issue_id": issue, "per_page": 5}
    )
    events_response = client.list_issue_events(events_plan)
    events = [domain.event_view(item) for item in _list(events_response, "events")]

    tag_plan = domain.plan_list_issue_tag_values(
        {"organization_slug": org, "issue_id": issue, "tag_key": "environment"}
    )
    tags_response = client.list_issue_tag_values(tag_plan)
    tag_values = [domain.tag_value_view(item) for item in _list(tags_response, "tag values")]

    evidence = {
        "ok": True,
        "origin": "https://sentry.io/api/0",
        "statuses": {
            "projects": projects_response.status,
            "teams": teams_response.status,
            "members": members_response.status,
            "issues": issues_response.status,
            "issue": issue_response.status,
            "events": events_response.status,
            "tag_values": tags_response.status,
        },
        "counts": {
            "projects": len(projects),
            "owners": len(owners),
            "issues": len(issues),
            "events": len(events),
            "tag_values": len(tag_values),
        },
        "issue": issue_view,
        "privacy": {
            "raw_events_omitted": True,
            "structured_user_fields_omitted": True,
            "text_fields_may_contain_application_data": True,
            "safe_event_tags": sorted(domain.SAFE_EVENT_TAG_KEYS),
        },
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
