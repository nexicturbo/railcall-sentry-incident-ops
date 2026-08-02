from __future__ import annotations

import copy
import json
import urllib.parse
from typing import Any

from tests.fixtures import EVENTS, MEMBERS, PROJECTS, TAG_VALUES, TEAMS, fresh_issue


class FakeResponse:
    def __init__(self, status: int, data: Any, headers: dict[str, str] | None = None):
        self.status = status
        self._body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.headers = headers or {}
        self.closed = False

    def getcode(self):
        return self.status

    def read(self, amount: int = -1):
        return self._body if amount < 0 else self._body[:amount]

    def close(self):
        self.closed = True


class ScenarioOpener:
    """Stateful fake of documented Sentry endpoints; no external I/O."""

    def __init__(self):
        self.issue = fresh_issue()
        self.requests = []
        self.force_verify_mismatch = False
        self.link = (
            '<https://sentry.io/api/0/organizations/acme/issues/?cursor=next%3A1%3A0>; '
            'rel="next"; results="true"'
        )

    def __call__(self, request, timeout=0):
        self.requests.append(request)
        parsed = urllib.parse.urlparse(request.full_url)
        path = parsed.path
        method = request.get_method()
        if method == "PUT":
            patch = json.loads((request.data or b"{}").decode("utf-8"))
            if "status" in patch:
                self.issue["status"] = patch["status"]
            if "priority" in patch:
                self.issue["priority"] = patch["priority"]
            if "assignedTo" in patch:
                value = patch["assignedTo"]
                if value == "":
                    self.issue["assignedTo"] = None
                else:
                    kind, owner_id = value.split(":", 1)
                    self.issue["assignedTo"] = {"type": kind, "id": owner_id, "name": "Updated"}
            if "hasSeen" in patch:
                self.issue["hasSeen"] = patch["hasSeen"]
            if "inbox" in patch:
                self.issue["inbox"] = patch["inbox"]
            if self.force_verify_mismatch and "status" in patch:
                self.issue["status"] = "unresolved"
            return FakeResponse(200, copy.deepcopy(self.issue))
        if path.endswith("/projects/"):
            return FakeResponse(200, PROJECTS, {"Link": self.link})
        if path.endswith("/teams/"):
            return FakeResponse(200, TEAMS)
        if path.endswith("/members/"):
            return FakeResponse(200, MEMBERS)
        if path.endswith("/issues/"):
            return FakeResponse(200, [copy.deepcopy(self.issue)], {"Link": self.link})
        if path.endswith("/issues/42/events/"):
            return FakeResponse(200, EVENTS, {"Link": self.link})
        if "/issues/42/tags/" in path:
            return FakeResponse(200, TAG_VALUES)
        if path.endswith("/issues/42/"):
            return FakeResponse(200, copy.deepcopy(self.issue))
        raise AssertionError(f"unexpected fake request: {method} {path}")
