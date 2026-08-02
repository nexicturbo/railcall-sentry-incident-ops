"""Fixed-origin, bearer-authenticated Sentry API transport."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping


API_ORIGIN = "https://sentry.io"
API_ROOT = "/api/0"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
USER_AGENT = "RailCall-Sentry-Incident-Ops/0.1"


class SentryApiError(RuntimeError):
    """A sanitized, operator-actionable Sentry API failure."""


@dataclass(frozen=True)
class ApiResponse:
    status: int
    data: Any
    next_cursor: str | None = None
    previous_cursor: str | None = None


def token_from_vault(vault_get: Callable[[str], Any]) -> str:
    entry = vault_get("sentry")
    if isinstance(entry, Mapping):
        value = next(
            (
                entry.get(key)
                for key in (
                    "SENTRY_AUTH_TOKEN",
                    "auth_token",
                    "api_key",
                    "token",
                )
                if entry.get(key)
            ),
            None,
        )
    else:
        value = entry
    if not isinstance(value, str) or not value.strip():
        raise SentryApiError(
            "no Sentry token found in the RailCall vault; save SENTRY_AUTH_TOKEN under provider sentry"
        )
    token = value.strip()
    if len(token) > 4096 or any(ord(ch) < 33 for ch in token):
        raise SentryApiError("the Sentry vault token has an invalid shape")
    return token


def _safe_error_message(body: bytes) -> str:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        return "request failed"
    if isinstance(parsed, Mapping):
        for field in ("detail", "message", "error"):
            value = parsed.get(field)
            if isinstance(value, str) and value.strip():
                clean = value.replace("\r", " ").replace("\n", " ").strip()
                return clean[:300]
    return "request failed"


def _headers_get(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    try:
        value = headers.get(name, "")
    except Exception:
        return ""
    return str(value or "")


_LINK_PART_RE = re.compile(
    r'<(?P<url>[^>]+)>\s*;(?P<params>[^,]+)(?:,|$)', re.IGNORECASE
)


def parse_pagination(link_header: str) -> tuple[str | None, str | None]:
    next_cursor: str | None = None
    previous_cursor: str | None = None
    for match in _LINK_PART_RE.finditer(link_header or ""):
        params = match.group("params")
        rel_match = re.search(r'rel="(?P<rel>next|previous)"', params, re.IGNORECASE)
        results_match = re.search(r'results="(?P<results>true|false)"', params, re.IGNORECASE)
        if not rel_match or (results_match and results_match.group("results").lower() != "true"):
            continue
        parsed = urllib.parse.urlparse(match.group("url"))
        if parsed.scheme != "https" or parsed.netloc.lower() != "sentry.io":
            continue
        cursor_values = urllib.parse.parse_qs(parsed.query).get("cursor") or []
        if not cursor_values:
            continue
        cursor = cursor_values[0][:512]
        if rel_match.group("rel").lower() == "next":
            next_cursor = cursor
        else:
            previous_cursor = cursor
    return next_cursor, previous_cursor


class SentryClient:
    def __init__(
        self,
        token: str,
        *,
        opener: Callable[..., Any] | None = None,
        timeout: int = 20,
    ) -> None:
        if not isinstance(token, str) or not token:
            raise SentryApiError("a Sentry token is required")
        self._token = token
        self._opener = opener or urllib.request.urlopen
        self._timeout = timeout

    def _scrub_text(self, value: Any) -> str:
        return str(value).replace(self._token, "[REDACTED]")

    def _scrub_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._scrub_text(value)
        if isinstance(value, list):
            return [self._scrub_value(item) for item in value]
        if isinstance(value, Mapping):
            return {
                self._scrub_text(key) if isinstance(key, str) else key: self._scrub_value(item)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _segment(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise SentryApiError("a required Sentry path identifier is empty")
        return urllib.parse.quote(text, safe="")

    def _url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        if not path.startswith("/") or "//" in path or "?" in path or "#" in path:
            raise SentryApiError("refused an invalid Sentry API path")
        query_items: list[tuple[str, str]] = []
        for key, value in (params or {}).items():
            if value is None or value == "":
                continue
            values = value if isinstance(value, (list, tuple)) else (value,)
            query_items.extend((str(key), str(item)) for item in values)
        query = urllib.parse.urlencode(query_items)
        return f"{API_ORIGIN}{API_ROOT}{path}" + (f"?{query}" if query else "")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> ApiResponse:
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": USER_AGENT,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._url(path, params), data=data, method=method, headers=headers
        )
        try:
            response = self._opener(request, timeout=self._timeout)
            try:
                status = int(getattr(response, "status", None) or response.getcode())
                body = response.read(MAX_RESPONSE_BYTES + 1)
                response_headers = getattr(response, "headers", None)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(32768)
            except Exception:
                body = b""
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            message = self._scrub_text(_safe_error_message(body))
            retry_after = _headers_get(getattr(exc, "headers", None), "Retry-After")[:32]
            suffix = f"; retry after {retry_after} seconds" if exc.code == 429 and retry_after else ""
            raise SentryApiError(f"Sentry API HTTP {exc.code}: {message}{suffix}") from None
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            reason = getattr(exc, "reason", None)
            clean = self._scrub_text(reason or "connection failed").replace("\r", " ").replace("\n", " ")[:200]
            raise SentryApiError(f"Sentry network error: {clean}") from None
        except OSError as exc:
            clean = self._scrub_text(exc).replace("\r", " ").replace("\n", " ")[:200]
            raise SentryApiError(f"Sentry network error: {clean or type(exc).__name__}") from None

        if len(body) > MAX_RESPONSE_BYTES:
            raise SentryApiError("Sentry response exceeded the 4 MiB safety limit")
        if status < 200 or status >= 300:
            raise SentryApiError(
                f"Sentry API HTTP {status}: {self._scrub_text(_safe_error_message(body))}"
            )
        if not body:
            parsed: Any = {}
        else:
            try:
                parsed = self._scrub_value(json.loads(body.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise SentryApiError(f"Sentry API HTTP {status}: response was not valid JSON") from None
        next_cursor, previous_cursor = parse_pagination(_headers_get(response_headers, "Link"))
        return ApiResponse(status, parsed, next_cursor, previous_cursor)

    def list_projects(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        return self._request(
            "GET",
            f"/organizations/{org}/projects/",
            params={"query": plan.get("query"), "cursor": plan.get("cursor"), "per_page": plan["per_page"]},
        )

    def list_teams(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        return self._request(
            "GET",
            f"/organizations/{org}/teams/",
            params={"per_page": plan["per_page"], "cursor": plan.get("teams_cursor")},
        )

    def list_members(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        return self._request(
            "GET",
            f"/organizations/{org}/members/",
            params={"per_page": plan["per_page"], "cursor": plan.get("members_cursor")},
        )

    def list_issues(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        return self._request(
            "GET",
            f"/organizations/{org}/issues/",
            params={
                "query": plan.get("query"),
                "project": plan.get("project"),
                "environment": plan.get("environment"),
                "statsPeriod": plan.get("stats_period"),
                "sort": plan.get("sort"),
                "cursor": plan.get("cursor"),
                "limit": plan.get("limit"),
            },
        )

    def get_issue(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        issue = self._segment(plan["issue_id"])
        return self._request(
            "GET",
            f"/organizations/{org}/issues/{issue}/",
            params={"collapse": ["release", "stats", "tags"]},
        )

    def list_issue_events(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        issue = self._segment(plan["issue_id"])
        return self._request(
            "GET",
            f"/organizations/{org}/issues/{issue}/events/",
            params={
                "environment": plan.get("environment"),
                "statsPeriod": plan.get("stats_period"),
                "cursor": plan.get("cursor"),
                "per_page": plan.get("per_page"),
                "full": "false",
            },
        )

    def list_issue_tag_values(self, plan: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        issue = self._segment(plan["issue_id"])
        key = self._segment(plan["tag_key"])
        return self._request(
            "GET",
            f"/organizations/{org}/issues/{issue}/tags/{key}/values/",
            params={"environment": plan.get("environment"), "sort": plan.get("sort")},
        )

    def update_issue(self, plan: Mapping[str, Any], patch: Mapping[str, Any]) -> ApiResponse:
        org = self._segment(plan["organization_slug"])
        issue = self._segment(plan["issue_id"])
        return self._request(
            "PUT", f"/organizations/{org}/issues/{issue}/", payload=dict(patch)
        )
