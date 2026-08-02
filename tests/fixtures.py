from __future__ import annotations

import copy


PROJECTS = [
    {
        "id": "100",
        "slug": "web-api",
        "name": "Web API",
        "platform": "python",
        "status": "active",
        "dateCreated": "2026-07-01T12:00:00Z",
    }
]

TEAMS = [{"id": "7", "slug": "incident-response", "name": "Incident Response"}]

MEMBERS = [
    {
        "id": "member-8",
        "user": {
            "id": "8",
            "name": "Ada Operator",
            "email": "ada@example.invalid",
            "username": "ada@example.invalid",
            "isActive": True,
        },
    },
    {
        "id": "member-9",
        "user": {
            "id": "9",
            "name": "Inactive Person",
            "email": "inactive@example.invalid",
            "isActive": False,
        },
    },
]

ISSUE = {
    "id": "42",
    "shortId": "WEB-42",
    "title": "Checkout request failed",
    "culprit": "checkout.views.submit",
    "status": "unresolved",
    "substatus": "ongoing",
    "priority": "high",
    "assignedTo": {"type": "team", "id": "7", "name": "Incident Response"},
    "hasSeen": False,
    "inbox": True,
    "firstSeen": "2026-08-01T12:00:00Z",
    "lastSeen": "2026-08-02T12:00:00Z",
    "count": "17",
    "userCount": 3,
    "project": {"id": "100", "slug": "web-api", "name": "Web API"},
    "metadata": {"secret": "raw-event-data"},
}

EVENTS = [
    {
        "id": "evt-internal-1",
        "eventID": "a" * 32,
        "dateCreated": "2026-08-02T12:00:00Z",
        "title": "Checkout request failed",
        "message": "Payment provider returned 503\nretrying",
        "platform": "python",
        "event.type": "error",
        "user": {"email": "customer@example.invalid", "ip_address": "192.0.2.7"},
        "contexts": {"request": {"cookies": "secret"}},
        "tags": [
            {"key": "environment", "value": "production"},
            {"key": "release", "value": "web@1.2.3"},
            {"key": "user.email", "value": "customer@example.invalid"},
        ],
    }
]

TAG_VALUES = [
    {
        "value": "production",
        "count": 17,
        "firstSeen": "2026-08-01T12:00:00Z",
        "lastSeen": "2026-08-02T12:00:00Z",
    }
]


def fresh_issue():
    return copy.deepcopy(ISSUE)
