from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.parse

from sentry_incident_ops.transport import (
    MAX_RESPONSE_BYTES,
    SentryApiError,
    SentryClient,
    parse_pagination,
    token_from_vault,
)
from tests.fakes import FakeResponse, ScenarioOpener


class VaultTests(unittest.TestCase):
    def test_canonical_token_field(self):
        self.assertEqual(token_from_vault(lambda _: {"SENTRY_AUTH_TOKEN": "abc"}), "abc")

    def test_legacy_token_field(self):
        self.assertEqual(token_from_vault(lambda _: {"auth_token": "abc"}), "abc")

    def test_raw_string_token(self):
        self.assertEqual(token_from_vault(lambda _: "abc"), "abc")

    def test_missing_token(self):
        with self.assertRaisesRegex(SentryApiError, "no Sentry token"):
            token_from_vault(lambda _: {})

    def test_control_character_token_rejected(self):
        with self.assertRaises(SentryApiError):
            token_from_vault(lambda _: {"token": "bad\ntoken"})


class PaginationTests(unittest.TestCase):
    def test_next_cursor(self):
        header = '<https://sentry.io/api/0/x/?cursor=next%3A1%3A0>; rel="next"; results="true"'
        self.assertEqual(parse_pagination(header), ("next:1:0", None))

    def test_false_result_ignored(self):
        header = '<https://sentry.io/api/0/x/?cursor=nope>; rel="next"; results="false"'
        self.assertEqual(parse_pagination(header), (None, None))

    def test_previous_and_next(self):
        header = (
            '<https://sentry.io/api/0/x/?cursor=prev>; rel="previous"; results="true", '
            '<https://sentry.io/api/0/x/?cursor=next>; rel="next"; results="true"'
        )
        self.assertEqual(parse_pagination(header), ("next", "prev"))

    def test_foreign_origin_ignored(self):
        header = '<https://evil.invalid/?cursor=steal>; rel="next"; results="true"'
        self.assertEqual(parse_pagination(header), (None, None))


class ClientTests(unittest.TestCase):
    def test_list_projects_is_fixed_origin(self):
        opener = ScenarioOpener()
        client = SentryClient("secret-token", opener=opener)
        client.list_projects({"organization_slug": "acme", "query": None, "cursor": None, "per_page": 50})
        self.assertTrue(opener.requests[0].full_url.startswith("https://sentry.io/api/0/organizations/acme/projects/"))

    def test_path_segments_are_quoted(self):
        seen = []

        def opener(request, timeout=0):
            seen.append(request)
            return FakeResponse(200, {})

        SentryClient("token", opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42/../../x"})
        self.assertIn("42%2F..%2F..%2Fx", seen[0].full_url)

    def test_bearer_header_present(self):
        opener = ScenarioOpener()
        SentryClient("secret-token", opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42"})
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer secret-token")

    def test_none_params_omitted(self):
        opener = ScenarioOpener()
        SentryClient("token", opener=opener).list_projects({"organization_slug": "acme", "query": None, "cursor": None, "per_page": 50})
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.requests[0].full_url).query)
        self.assertEqual(query, {"per_page": ["50"]})

    def test_sentry_camelcase_params(self):
        opener = ScenarioOpener()
        plan = {"organization_slug": "acme", "query": "is:unresolved", "project": None, "environment": "prod", "stats_period": "14d", "sort": "date", "cursor": None, "limit": 25}
        SentryClient("token", opener=opener).list_issues(plan)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.requests[0].full_url).query)
        self.assertEqual(query["statsPeriod"], ["14d"])

    def test_get_issue_collapses_large_sections(self):
        opener = ScenarioOpener()
        SentryClient("token", opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42"})
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.requests[0].full_url).query)
        self.assertEqual(query["collapse"], ["release", "stats", "tags"])

    def test_event_request_explicitly_disables_full_payload(self):
        opener = ScenarioOpener()
        plan = {"organization_slug": "acme", "issue_id": "42", "environment": None, "stats_period": None, "cursor": None, "per_page": 20}
        SentryClient("token", opener=opener).list_issue_events(plan)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(opener.requests[0].full_url).query)
        self.assertEqual(query["full"], ["false"])

    def test_pagination_returned(self):
        response = SentryClient("token", opener=ScenarioOpener()).list_projects({"organization_slug": "acme", "query": None, "cursor": None, "per_page": 50})
        self.assertEqual(response.next_cursor, "next:1:0")

    def test_update_uses_put_and_exact_json(self):
        opener = ScenarioOpener()
        client = SentryClient("token", opener=opener)
        client.update_issue({"organization_slug": "acme", "issue_id": "42"}, {"status": "resolved"})
        request = opener.requests[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(json.loads(request.data), {"status": "resolved"})

    def test_invalid_json_rejected(self):
        with self.assertRaisesRegex(SentryApiError, "not valid JSON"):
            SentryClient("token", opener=lambda *_args, **_kwargs: FakeResponse(200, b"not-json")).get_issue({"organization_slug": "acme", "issue_id": "42"})

    def test_large_response_rejected(self):
        body = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(SentryApiError, "4 MiB"):
            SentryClient("token", opener=lambda *_args, **_kwargs: FakeResponse(200, body)).get_issue({"organization_slug": "acme", "issue_id": "42"})

    def test_http_error_is_sanitized_and_actionable(self):
        token = "super-secret-token"

        def opener(request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                io.BytesIO(b'{"detail":"missing event:write scope"}'),
            )

        with self.assertRaisesRegex(SentryApiError, "missing event:write scope") as caught:
            SentryClient(token, opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42"})
        self.assertNotIn(token, str(caught.exception))

    def test_provider_echo_of_token_is_redacted_from_error(self):
        token = "echoed-secret-token"

        def opener(request, timeout=0):
            body = json.dumps({"detail": f"bad credential {token}"}).encode()
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(body))

        with self.assertRaises(SentryApiError) as caught:
            SentryClient(token, opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42"})
        self.assertNotIn(token, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_provider_echo_of_token_is_redacted_from_success(self):
        token = "echoed-secret-token"
        response = SentryClient(
            token,
            opener=lambda *_args, **_kwargs: FakeResponse(200, {"message": token, token: "value"}),
        ).get_issue({"organization_slug": "acme", "issue_id": "42"})
        self.assertNotIn(token, repr(response.data))

    def test_rate_limit_retry_after(self):
        def opener(request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Limited",
                {"Retry-After": "12"},
                io.BytesIO(b'{"detail":"rate limited"}'),
            )

        with self.assertRaisesRegex(SentryApiError, "retry after 12 seconds"):
            SentryClient("token", opener=opener).get_issue({"organization_slug": "acme", "issue_id": "42"})


if __name__ == "__main__":
    unittest.main()
