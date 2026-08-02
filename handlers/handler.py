"""RailCall command handlers for Sentry Incident Operations Airlock."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from sentry_incident_ops import domain
from sentry_incident_ops.proof import safety_proof
from sentry_incident_ops.transport import ApiResponse, SentryClient, token_from_vault


try:
    __rc_helpers__
except NameError:  # Normal imports in deterministic tests.
    __rc_helpers__ = {}

_test_vault_get: Callable[[str], Any] | None = None
_test_opener: Callable[..., Any] | None = None


def configure_for_tests(
    *, vault_get: Callable[[str], Any] | None = None, opener: Callable[..., Any] | None = None
) -> None:
    """Inject deterministic boundaries; never used by a RailCall station."""
    global _test_vault_get, _test_opener
    _test_vault_get = vault_get
    _test_opener = opener


def _client() -> SentryClient:
    vault_get = _test_vault_get or __rc_helpers__.get("vault_get")
    if not callable(vault_get):
        raise RuntimeError("RailCall did not inject the vault_get helper")
    return SentryClient(token_from_vault(vault_get), opener=_test_opener)


def _list_data(response: ApiResponse, label: str) -> list[Any]:
    if not isinstance(response.data, list):
        raise RuntimeError(f"Sentry returned an invalid {label} response")
    return response.data


def _read_result(
    command: str,
    plan: Mapping[str, Any],
    response: ApiResponse,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    result["http_status"] = response.status
    result["safety_proof"] = safety_proof(
        command,
        (("intent", dict(plan)), ("observed", {"status": response.status, "result": payload})),
    )
    return result


def sentry_list_projects(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_list_projects(inputs)
    response = _client().list_projects(plan)
    projects = [domain.project_view(item) for item in _list_data(response, "projects")]
    result = _read_result(
        "sentry.list_projects",
        plan,
        response,
        {"projects": projects, "next_cursor": response.next_cursor or ""},
    )
    return result, None


def sentry_list_owners(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_list_owners(inputs)
    client = _client()
    teams = client.list_teams(plan)
    members = client.list_members(plan)
    owners = domain.owners_view(
        _list_data(teams, "teams"), _list_data(members, "members"), query=plan["query"]
    )
    status = max(teams.status, members.status)
    synthetic = ApiResponse(status, owners)
    result = _read_result(
        "sentry.list_owners",
        plan,
        synthetic,
        {
            "owners": owners,
            "next_teams_cursor": teams.next_cursor or "",
            "next_members_cursor": members.next_cursor or "",
            "truncated": bool(teams.next_cursor or members.next_cursor),
            "privacy": {"emails_omitted": True, "inactive_members_omitted": True},
        },
    )
    return result, None


def sentry_list_issues(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_list_issues(inputs)
    response = _client().list_issues(plan)
    issues = [domain.issue_view(item) for item in _list_data(response, "issues")]
    result = _read_result(
        "sentry.list_issues",
        plan,
        response,
        {"issues": issues, "next_cursor": response.next_cursor or ""},
    )
    return result, None


def sentry_get_issue(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_get_issue(inputs)
    response = _client().get_issue(plan)
    if not isinstance(response.data, Mapping):
        raise RuntimeError("Sentry returned an invalid issue response")
    result = _read_result(
        "sentry.get_issue", plan, response, {"issue": domain.issue_view(response.data)}
    )
    return result, None


def sentry_list_issue_events(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_list_issue_events(inputs)
    response = _client().list_issue_events(plan)
    events = [domain.event_view(item) for item in _list_data(response, "events")]
    payload = {
        "events": events,
        "next_cursor": response.next_cursor or "",
        "privacy": {
            "raw_payloads_omitted": True,
            "structured_user_fields_omitted": True,
            "text_fields_may_contain_application_data": True,
            "allowed_tags": sorted(domain.SAFE_EVENT_TAG_KEYS),
        },
    }
    return _read_result("sentry.list_issue_events", plan, response, payload), None


def sentry_list_issue_tag_values(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_list_issue_tag_values(inputs)
    response = _client().list_issue_tag_values(plan)
    values = [domain.tag_value_view(item) for item in _list_data(response, "tag values")]
    payload = {
        "tag_key": plan["tag_key"],
        "values": values,
        "privacy": {"safe_operational_tag_allowlist_enforced": True},
    }
    return _read_result("sentry.list_issue_tag_values", plan, response, payload), None


def _write_issue(
    command: str,
    plan: Mapping[str, Any],
    *,
    preconditions: Mapping[str, Any],
    patch: Mapping[str, Any],
    targets: Mapping[str, Any],
) -> dict[str, Any]:
    client = _client()
    observed_response = client.get_issue(plan)
    if not isinstance(observed_response.data, Mapping):
        raise RuntimeError("Sentry returned an invalid issue response")
    before = domain.issue_state(observed_response.data)
    for field, expected in preconditions.items():
        domain.require_precondition(field, expected, before.get(field))

    if all(before.get(field) == target for field, target in targets.items()):
        decision = {"write": False, "reason": "already_at_target"}
        after = dict(before)
        status = observed_response.status
        changed = False
    else:
        decision = {"write": True, "fields": sorted(patch)}
        write_response = client.update_issue(plan, patch)
        verified_response = client.get_issue(plan)
        if not isinstance(verified_response.data, Mapping):
            raise RuntimeError("Sentry returned an invalid verification response")
        after = domain.issue_state(verified_response.data)
        for field, target in targets.items():
            if after.get(field) != target:
                raise RuntimeError(
                    f"Sentry write could not be verified: expected {field}={target!r}, got {after.get(field)!r}"
                )
        status = write_response.status
        changed = True

    outcome = {
        "issue_id": plan["issue_id"],
        "before": before,
        "after": after,
        "changed": changed,
        "http_status": status,
    }
    outcome["safety_proof"] = safety_proof(
        command,
        (
            ("intent", dict(plan)),
            ("observed", before),
            ("decision", decision),
            ("verified", {"after": after, "changed": changed, "http_status": status}),
        ),
    )
    return outcome


def sentry_set_issue_status(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_set_issue_status(inputs)
    result = _write_issue(
        "sentry.set_issue_status",
        plan,
        preconditions={"status": plan["expected_status"]},
        patch={"status": plan["status"]},
        targets={"status": plan["status"]},
    )
    return result, None


def sentry_assign_issue(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_assign_issue(inputs)
    assigned_to = plan["assigned_to"]
    result = _write_issue(
        "sentry.assign_issue",
        plan,
        preconditions={"assignee": plan["expected_assignee"]},
        patch={"assignedTo": "" if assigned_to == "unassigned" else assigned_to},
        targets={"assignee": assigned_to},
    )
    return result, None


def sentry_set_issue_priority(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_set_issue_priority(inputs)
    result = _write_issue(
        "sentry.set_issue_priority",
        plan,
        preconditions={"priority": plan["expected_priority"]},
        patch={"priority": plan["priority"]},
        targets={"priority": plan["priority"]},
    )
    return result, None


def sentry_mark_issue_reviewed(inputs: Any, stamp: Any) -> tuple[dict[str, Any], None]:
    plan = domain.plan_mark_issue_reviewed(inputs)
    result = _write_issue(
        "sentry.mark_issue_reviewed",
        plan,
        preconditions={"inbox": plan["expected_inbox"]},
        patch={"inbox": False},
        targets={"inbox": False},
    )
    return result, None
