from __future__ import annotations

import unittest

from sentry_incident_ops import domain
from tests.fixtures import EVENTS, ISSUE, MEMBERS, TEAMS


class PlanningTests(unittest.TestCase):
    def test_projects_defaults(self):
        plan = domain.plan_list_projects({"organization_slug": "acme"})
        self.assertEqual(plan["per_page"], 50)
        self.assertIsNone(plan["cursor"])

    def test_org_allows_expected_slug(self):
        self.assertEqual(domain.plan_get_issue({"organization_slug": "acme.io", "issue_id": "42"})["organization_slug"], "acme.io")

    def test_org_rejects_path_injection(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_get_issue({"organization_slug": "../acme", "issue_id": "42"})

    def test_control_character_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "query": "boom\nsecret"})

    def test_limit_maximum(self):
        self.assertEqual(domain.plan_list_issues({"organization_slug": "acme", "limit": 100})["limit"], 100)

    def test_limit_too_large_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "limit": 101})

    def test_fractional_limit_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "limit": 1.5})

    def test_boolean_limit_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "limit": True})

    def test_valid_stats_period(self):
        plan = domain.plan_list_issues({"organization_slug": "acme", "stats_period": "14d"})
        self.assertEqual(plan["stats_period"], "14d")

    def test_minute_stats_period(self):
        plan = domain.plan_list_issue_events({"organization_slug": "acme", "issue_id": "42", "stats_period": "30m"})
        self.assertEqual(plan["stats_period"], "30m")

    def test_invalid_stats_period(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "stats_period": "forever"})

    def test_invalid_issue_sort(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issues({"organization_slug": "acme", "sort": "drop-table"})

    def test_current_issue_sorts(self):
        for sort in ("inbox", "recommended", "trends"):
            self.assertEqual(domain.plan_list_issues({"organization_slug": "acme", "sort": sort})["sort"], sort)

    def test_owner_cursors_are_independent(self):
        plan = domain.plan_list_owners({"organization_slug": "acme", "teams_cursor": "t:1", "members_cursor": "m:1"})
        self.assertEqual((plan["teams_cursor"], plan["members_cursor"]), ("t:1", "m:1"))

    def test_safe_tag_key_allowed(self):
        plan = domain.plan_list_issue_tag_values({"organization_slug": "acme", "issue_id": "42", "tag_key": "release"})
        self.assertEqual(plan["tag_key"], "release")

    def test_pii_tag_key_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_list_issue_tag_values({"organization_slug": "acme", "issue_id": "42", "tag_key": "user.email"})

    def test_status_choices(self):
        for value in domain.ISSUE_STATUSES:
            plan = domain.plan_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "unresolved", "status": value})
            self.assertEqual(plan["status"], value)

    def test_unknown_status_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_set_issue_status({"organization_slug": "acme", "issue_id": "42", "expected_status": "unresolved", "status": "deleted"})

    def test_owner_ref_team(self):
        plan = domain.plan_assign_issue({"organization_slug": "acme", "issue_id": "42", "expected_assignee": "unassigned", "assigned_to": "team:7"})
        self.assertEqual(plan["assigned_to"], "team:7")

    def test_owner_ref_email_rejected(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_assign_issue({"organization_slug": "acme", "issue_id": "42", "expected_assignee": "unassigned", "assigned_to": "person@example.com"})

    def test_priority_choices(self):
        plan = domain.plan_set_issue_priority({"organization_slug": "acme", "issue_id": "42", "expected_priority": "high", "priority": "medium"})
        self.assertEqual(plan["priority"], "medium")

    def test_review_booleans_are_strict(self):
        with self.assertRaises(domain.ValidationError):
            domain.plan_mark_issue_reviewed({"organization_slug": "acme", "issue_id": "42", "expected_inbox": "true"})


class ViewTests(unittest.TestCase):
    def test_issue_view_is_minimized(self):
        view = domain.issue_view(ISSUE)
        self.assertNotIn("metadata", view)
        self.assertNotIn("secret", repr(view))
        self.assertEqual(view["assignee"], "team:7")

    def test_issue_state_unassigned(self):
        changed = dict(ISSUE, assignedTo=None)
        self.assertEqual(domain.issue_state(changed)["assignee"], "unassigned")

    def test_event_view_drops_user_and_contexts(self):
        view = domain.event_view(EVENTS[0])
        self.assertNotIn("user", view)
        self.assertNotIn("contexts", view)
        self.assertNotIn("customer@example.invalid", repr(view))

    def test_event_view_keeps_only_safe_tags(self):
        tags = domain.event_view(EVENTS[0])["tags"]
        self.assertEqual(tags, {"environment": "production", "release": "web@1.2.3"})

    def test_event_text_is_one_line(self):
        self.assertEqual(domain.event_view(EVENTS[0])["message"], "Payment provider returned 503 retrying")

    def test_event_type_uses_documented_key(self):
        self.assertEqual(domain.event_view(EVENTS[0])["type"], "error")

    def test_owners_omit_email_and_inactive_member(self):
        owners = domain.owners_view(TEAMS, MEMBERS)
        rendered = repr(owners)
        self.assertNotIn("@example.invalid", rendered)
        self.assertNotIn("Inactive Person", rendered)
        self.assertEqual({o["ref"] for o in owners}, {"team:7", "user:8"})

    def test_owners_query(self):
        owners = domain.owners_view(TEAMS, MEMBERS, query="incident")
        self.assertEqual([o["ref"] for o in owners], ["team:7"])

    def test_precondition_passes(self):
        domain.require_precondition("status", "open", "open")

    def test_precondition_failure_is_explicit(self):
        with self.assertRaisesRegex(domain.PreconditionFailed, "stale approval"):
            domain.require_precondition("status", "open", "closed")


if __name__ == "__main__":
    unittest.main()
