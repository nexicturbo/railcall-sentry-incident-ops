from __future__ import annotations

import json
import unittest

from handlers import handler
from sentry_incident_ops import domain
from tests.fakes import ScenarioOpener


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.opener = ScenarioOpener()
        handler.configure_for_tests(
            vault_get=lambda _: {"SENTRY_AUTH_TOKEN": "test-secret-token"},
            opener=self.opener,
        )

    def tearDown(self):
        handler.configure_for_tests(vault_get=None, opener=None)

    def test_list_projects(self):
        result, error = handler.sentry_list_projects({"organization_slug": "acme"}, {})
        self.assertIsNone(error)
        self.assertEqual(result["projects"][0]["slug"], "web-api")
        self.assertEqual(result["next_cursor"], "next:1:0")

    def test_list_owners_omits_pii(self):
        result, _ = handler.sentry_list_owners({"organization_slug": "acme"}, {})
        self.assertNotIn("@example.invalid", repr(result))
        self.assertEqual({owner["ref"] for owner in result["owners"]}, {"team:7", "user:8"})

    def test_list_owners_query(self):
        result, _ = handler.sentry_list_owners({"organization_slug": "acme", "query": "ada"}, {})
        self.assertEqual([owner["ref"] for owner in result["owners"]], ["user:8"])

    def test_list_issues(self):
        result, _ = handler.sentry_list_issues({"organization_slug": "acme"}, {})
        self.assertEqual(result["issues"][0]["short_id"], "WEB-42")

    def test_get_issue(self):
        result, _ = handler.sentry_get_issue({"organization_slug": "acme", "issue_id": "42"}, {})
        self.assertEqual(result["issue"]["status"], "unresolved")

    def test_list_events_is_privacy_minimized(self):
        result, _ = handler.sentry_list_issue_events({"organization_slug": "acme", "issue_id": "42"}, {})
        rendered = repr(result)
        self.assertNotIn("customer@example.invalid", rendered)
        self.assertNotIn("cookies", rendered)
        self.assertTrue(result["privacy"]["raw_payloads_omitted"])

    def test_list_safe_tag_values(self):
        result, _ = handler.sentry_list_issue_tag_values({"organization_slug": "acme", "issue_id": "42", "tag_key": "environment"}, {})
        self.assertEqual(result["values"][0]["value"], "production")

    def test_status_write_fetches_mutates_and_verifies(self):
        result, _ = handler.sentry_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "unresolved", "status": "resolved"}, {})
        self.assertTrue(result["changed"])
        self.assertEqual(result["after"]["status"], "resolved")
        self.assertEqual([request.get_method() for request in self.opener.requests], ["GET", "PUT", "GET"])

    def test_status_noop_is_idempotent(self):
        result, _ = handler.sentry_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "unresolved", "status": "unresolved"}, {})
        self.assertFalse(result["changed"])
        self.assertEqual([request.get_method() for request in self.opener.requests], ["GET"])

    def test_stale_status_refuses_before_put(self):
        with self.assertRaises(domain.PreconditionFailed):
            handler.sentry_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "resolved", "status": "ignored"}, {})
        self.assertEqual([request.get_method() for request in self.opener.requests], ["GET"])

    def test_verification_mismatch_fails_loudly(self):
        self.opener.force_verify_mismatch = True
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            handler.sentry_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "unresolved", "status": "resolved"}, {})

    def test_assign_team(self):
        result, _ = handler.sentry_assign_issue({"organization_slug": "acme", "issue_id": "42", "expected_assignee": "team:7", "assigned_to": "user:8"}, {})
        self.assertEqual(result["after"]["assignee"], "user:8")
        self.assertEqual(json.loads(self.opener.requests[1].data), {"assignedTo": "user:8"})

    def test_unassign_uses_documented_empty_string(self):
        handler.sentry_assign_issue({"organization_slug": "acme", "issue_id": "42", "expected_assignee": "team:7", "assigned_to": "unassigned"}, {})
        self.assertEqual(json.loads(self.opener.requests[1].data), {"assignedTo": ""})

    def test_set_priority(self):
        result, _ = handler.sentry_set_issue_priority({"organization_slug": "acme", "issue_id": "42", "expected_priority": "high", "priority": "medium"}, {})
        self.assertEqual(result["after"]["priority"], "medium")

    def test_mark_reviewed(self):
        result, _ = handler.sentry_mark_issue_reviewed({"organization_slug": "acme", "issue_id": "42", "expected_inbox": True}, {})
        self.assertFalse(result["after"]["inbox"])
        self.assertEqual(json.loads(self.opener.requests[1].data), {"inbox": False})

    def test_mark_reviewed_stale_inbox_refuses(self):
        with self.assertRaises(domain.PreconditionFailed):
            handler.sentry_mark_issue_reviewed({"organization_slug": "acme", "issue_id": "42", "expected_inbox": False}, {})
        self.assertEqual(len(self.opener.requests), 1)

    def test_write_proof_has_four_phases(self):
        result, _ = handler.sentry_set_issue_priority({"organization_slug": "acme", "issue_id": "42", "expected_priority": "high", "priority": "low"}, {})
        self.assertEqual([entry["phase"] for entry in result["safety_proof"]["chain"]], ["intent", "observed", "decision", "verified"])

    def test_token_never_appears_in_result(self):
        result, _ = handler.sentry_get_issue({"organization_slug": "acme", "issue_id": "42"}, {})
        self.assertNotIn("test-secret-token", repr(result))


if __name__ == "__main__":
    unittest.main()
