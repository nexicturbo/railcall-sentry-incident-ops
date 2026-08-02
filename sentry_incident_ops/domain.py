"""Validation, planning, and privacy-minimized Sentry response views.

This module is deliberately free of network, vault, process, and filesystem I/O.
Handlers validate and normalize an approved intent here before any API call.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


class ValidationError(ValueError):
    """An operator-correctable input validation failure."""


class PreconditionFailed(RuntimeError):
    """Live Sentry state no longer matches the approved intent."""


_ORG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PERIOD_RE = re.compile(r"^[1-9][0-9]{0,2}[dhmsw]$")
_OWNER_RE = re.compile(r"^(user|team):[A-Za-z0-9_-]{1,128}$")

ISSUE_STATUSES = frozenset({"resolved", "unresolved", "ignored", "muted"})
ISSUE_PRIORITIES = frozenset({"low", "medium", "high"})
ISSUE_SORTS = frozenset({"date", "new", "freq", "user", "inbox", "recommended", "trends"})
TAG_SORTS = frozenset({"date", "age", "count"})
SAFE_TAG_KEYS = frozenset(
    {
        "environment",
        "release",
        "level",
        "transaction",
        "handled",
        "mechanism",
    }
)
SAFE_EVENT_TAG_KEYS = SAFE_TAG_KEYS


def _mapping(inputs: Any) -> Mapping[str, Any]:
    if not isinstance(inputs, Mapping):
        raise ValidationError("inputs must be an object")
    return inputs


def required_text(
    inputs: Mapping[str, Any], name: str, *, max_length: int = 256
) -> str:
    value = inputs.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} is required")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"{name} must be at most {max_length} characters")
    if any(ord(ch) < 32 for ch in value):
        raise ValidationError(f"{name} contains a control character")
    return value


def optional_text(
    inputs: Mapping[str, Any], name: str, *, max_length: int = 512
) -> str | None:
    value = inputs.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string")
    value = value.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ValidationError(f"{name} must be at most {max_length} characters")
    if any(ord(ch) < 32 for ch in value):
        raise ValidationError(f"{name} contains a control character")
    return value


def bounded_int(
    inputs: Mapping[str, Any], name: str, *, default: int, minimum: int, maximum: int
) -> int:
    value = inputs.get(name, default)
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be an integer") from None
    if result < minimum or result > maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
    return result


def required_bool(inputs: Mapping[str, Any], name: str) -> bool:
    value = inputs.get(name)
    if not isinstance(value, bool):
        raise ValidationError(f"{name} must be true or false")
    return value


def organization(inputs: Mapping[str, Any]) -> str:
    slug = required_text(inputs, "organization_slug", max_length=64)
    if not _ORG_RE.fullmatch(slug):
        raise ValidationError(
            "organization_slug may contain only letters, numbers, dot, underscore, and hyphen"
        )
    return slug


def issue_id(inputs: Mapping[str, Any]) -> str:
    return required_text(inputs, "issue_id", max_length=128)


def _choice(value: str, name: str, choices: Iterable[str]) -> str:
    allowed = frozenset(choices)
    if value not in allowed:
        raise ValidationError(f"{name} must be one of: {', '.join(sorted(allowed))}")
    return value


def _period(inputs: Mapping[str, Any], name: str = "stats_period") -> str | None:
    value = optional_text(inputs, name, max_length=8)
    if value is not None and not _PERIOD_RE.fullmatch(value):
        raise ValidationError(f"{name} must look like 24h, 14d, or 30m")
    return value


def plan_list_projects(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {
        "organization_slug": organization(source),
        "query": optional_text(source, "query", max_length=200),
        "cursor": optional_text(source, "cursor", max_length=512),
        "per_page": bounded_int(source, "per_page", default=50, minimum=1, maximum=100),
    }


def plan_list_owners(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {
        "organization_slug": organization(source),
        "query": optional_text(source, "query", max_length=200),
        "teams_cursor": optional_text(source, "teams_cursor", max_length=512),
        "members_cursor": optional_text(source, "members_cursor", max_length=512),
        "per_page": bounded_int(source, "per_page", default=50, minimum=1, maximum=100),
    }


def plan_list_issues(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    sort = optional_text(source, "sort", max_length=16) or "date"
    _choice(sort, "sort", ISSUE_SORTS)
    return {
        "organization_slug": organization(source),
        "query": optional_text(source, "query", max_length=500),
        "project": optional_text(source, "project", max_length=128),
        "environment": optional_text(source, "environment", max_length=128),
        "stats_period": _period(source),
        "sort": sort,
        "cursor": optional_text(source, "cursor", max_length=512),
        "limit": bounded_int(source, "limit", default=25, minimum=1, maximum=100),
    }


def plan_get_issue(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {"organization_slug": organization(source), "issue_id": issue_id(source)}


def plan_list_issue_events(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "environment": optional_text(source, "environment", max_length=128),
        "stats_period": _period(source),
        "cursor": optional_text(source, "cursor", max_length=512),
        "per_page": bounded_int(source, "per_page", default=20, minimum=1, maximum=100),
    }


def plan_list_issue_tag_values(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    key = required_text(source, "tag_key", max_length=64)
    _choice(key, "tag_key", SAFE_TAG_KEYS)
    sort = optional_text(source, "sort", max_length=16) or "count"
    _choice(sort, "sort", TAG_SORTS)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "tag_key": key,
        "environment": optional_text(source, "environment", max_length=128),
        "sort": sort,
    }


def plan_set_issue_status(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    expected = required_text(source, "expected_status", max_length=32)
    target = required_text(source, "status", max_length=32)
    _choice(expected, "expected_status", ISSUE_STATUSES)
    _choice(target, "status", ISSUE_STATUSES)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "expected_status": expected,
        "status": target,
    }


def _owner_ref(source: Mapping[str, Any], name: str) -> str:
    value = required_text(source, name, max_length=140)
    if value != "unassigned" and not _OWNER_RE.fullmatch(value):
        raise ValidationError(f"{name} must be unassigned, user:<id>, or team:<id>")
    return value


def plan_assign_issue(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "expected_assignee": _owner_ref(source, "expected_assignee"),
        "assigned_to": _owner_ref(source, "assigned_to"),
    }


def plan_set_issue_priority(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    expected = required_text(source, "expected_priority", max_length=16)
    target = required_text(source, "priority", max_length=16)
    _choice(expected, "expected_priority", ISSUE_PRIORITIES)
    _choice(target, "priority", ISSUE_PRIORITIES)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "expected_priority": expected,
        "priority": target,
    }


def plan_mark_issue_reviewed(inputs: Any) -> dict[str, Any]:
    source = _mapping(inputs)
    return {
        "organization_slug": organization(source),
        "issue_id": issue_id(source),
        "expected_inbox": required_bool(source, "expected_inbox"),
    }


def _text(value: Any, *, maximum: int = 300) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:maximum]


def assignee_ref(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "unassigned"
    kind = _text(value.get("type"), maximum=16).lower()
    owner_id = _text(value.get("id"), maximum=128)
    if kind in {"user", "team"} and owner_id:
        return f"{kind}:{owner_id}"
    return "unassigned"


def project_view(project: Any) -> dict[str, Any]:
    item = project if isinstance(project, Mapping) else {}
    return {
        "id": _text(item.get("id"), maximum=128),
        "slug": _text(item.get("slug"), maximum=128),
        "name": _text(item.get("name"), maximum=200),
        "platform": _text(item.get("platform"), maximum=80),
        "status": _text(item.get("status"), maximum=40),
        "date_created": _text(item.get("dateCreated"), maximum=64),
    }


def issue_state(issue: Any) -> dict[str, Any]:
    item = issue if isinstance(issue, Mapping) else {}
    return {
        "status": _text(item.get("status"), maximum=32),
        "priority": _text(item.get("priority"), maximum=16),
        "assignee": assignee_ref(item.get("assignedTo")),
        "has_seen": bool(item.get("hasSeen", False)),
        "inbox": bool(item.get("inbox", False)),
    }


def issue_view(issue: Any) -> dict[str, Any]:
    item = issue if isinstance(issue, Mapping) else {}
    project = item.get("project") if isinstance(item.get("project"), Mapping) else {}
    state = issue_state(item)
    return {
        "id": _text(item.get("id"), maximum=128),
        "short_id": _text(item.get("shortId"), maximum=128),
        "title": _text(item.get("title"), maximum=300),
        "culprit": _text(item.get("culprit"), maximum=300),
        "status": state["status"],
        "substatus": _text(item.get("substatus"), maximum=48),
        "priority": state["priority"],
        "assignee": state["assignee"],
        "has_seen": state["has_seen"],
        "inbox": state["inbox"],
        "first_seen": _text(item.get("firstSeen"), maximum=64),
        "last_seen": _text(item.get("lastSeen"), maximum=64),
        "count": _text(item.get("count"), maximum=32),
        "user_count": int(item.get("userCount") or 0),
        "project": {
            "id": _text(project.get("id"), maximum=128),
            "slug": _text(project.get("slug"), maximum=128),
            "name": _text(project.get("name"), maximum=200),
        },
    }


def _safe_tags(tags: Any) -> dict[str, str]:
    if not isinstance(tags, list):
        return {}
    result: dict[str, str] = {}
    for tag in tags:
        if not isinstance(tag, Mapping):
            continue
        key = _text(tag.get("key"), maximum=64)
        if key not in SAFE_EVENT_TAG_KEYS:
            continue
        result[key] = _text(tag.get("value"), maximum=200)
    return result


def event_view(event: Any) -> dict[str, Any]:
    item = event if isinstance(event, Mapping) else {}
    return {
        "id": _text(item.get("id"), maximum=128),
        "event_id": _text(item.get("eventID") or item.get("eventId"), maximum=128),
        "date_created": _text(item.get("dateCreated"), maximum=64),
        "title": _text(item.get("title"), maximum=300),
        "message": _text(item.get("message"), maximum=300),
        "platform": _text(item.get("platform"), maximum=80),
        "type": _text(item.get("type") or item.get("event.type"), maximum=80),
        "tags": _safe_tags(item.get("tags")),
    }


def tag_value_view(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, Mapping) else {}
    return {
        "value": _text(item.get("value"), maximum=200),
        "count": int(item.get("count") or 0),
        "first_seen": _text(item.get("firstSeen"), maximum=64),
        "last_seen": _text(item.get("lastSeen"), maximum=64),
    }


def owners_view(teams: Any, members: Any, *, query: str | None = None) -> list[dict[str, Any]]:
    owners: list[dict[str, Any]] = []
    for raw in teams if isinstance(teams, list) else []:
        if not isinstance(raw, Mapping):
            continue
        owner_id = _text(raw.get("id"), maximum=128)
        if not owner_id:
            continue
        owners.append(
            {
                "ref": f"team:{owner_id}",
                "kind": "team",
                "id": owner_id,
                "name": _text(raw.get("name"), maximum=200),
                "slug": _text(raw.get("slug"), maximum=128),
            }
        )
    for raw in members if isinstance(members, list) else []:
        if not isinstance(raw, Mapping):
            continue
        user = raw.get("user") if isinstance(raw.get("user"), Mapping) else {}
        owner_id = _text(user.get("id") or raw.get("id"), maximum=128)
        if not owner_id or user.get("isActive") is False:
            continue
        owners.append(
            {
                "ref": f"user:{owner_id}",
                "kind": "user",
                "id": owner_id,
                "name": _text(user.get("name") or user.get("displayName"), maximum=200),
                "slug": "",
            }
        )
    if query:
        needle = query.casefold()
        owners = [
            owner
            for owner in owners
            if needle in owner["name"].casefold()
            or needle in owner["slug"].casefold()
            or needle in owner["ref"].casefold()
        ]
    return sorted(owners, key=lambda owner: (owner["kind"], owner["name"].casefold(), owner["id"]))


def require_precondition(field: str, expected: Any, observed: Any) -> None:
    if observed != expected:
        raise PreconditionFailed(
            f"stale approval: expected {field}={expected!r}, but Sentry now reports {observed!r}"
        )
