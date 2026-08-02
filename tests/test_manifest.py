from __future__ import annotations

import importlib
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "module.json").read_text(encoding="utf-8"))

    def test_manifest_v2(self):
        self.assertEqual(self.manifest["manifest_version"], 2)

    def test_contest_tag_present(self):
        self.assertIn("contest:2026Q3", self.manifest["description"])

    def test_exactly_ten_commands(self):
        self.assertEqual(len(self.manifest["commands"]), 10)

    def test_command_ids_unique(self):
        ids = [command["id"] for command in self.manifest["commands"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_handler_exists(self):
        module = importlib.import_module("handlers.handler")
        for command in self.manifest["commands"]:
            name = command["id"].replace(".", "_").replace("-", "_")
            self.assertTrue(callable(getattr(module, name, None)), name)

    def test_every_command_requires_receipt_and_preview(self):
        for command in self.manifest["commands"]:
            self.assertTrue(command["preview"], command["id"])
            self.assertTrue(command["receipt_required"], command["id"])

    def test_write_commands_are_airlocked(self):
        writes = [command for command in self.manifest["commands"] if command["mode"] != "read"]
        self.assertEqual(len(writes), 4)
        for command in writes:
            self.assertEqual(command["mode"], "write_requires_approval")
            self.assertEqual(command["side_effects"], "external")
            self.assertIn("expected_", " ".join(command["input_schema"]))

    def test_read_commands_declare_no_side_effects(self):
        for command in self.manifest["commands"]:
            if command["mode"] == "read":
                self.assertEqual(command["side_effects"], "none")

    def test_capabilities_are_minimal(self):
        self.assertEqual(self.manifest["requires"]["network"], ["sentry.io"])
        self.assertFalse(self.manifest["requires"]["subprocess"])
        self.assertEqual(self.manifest["requires"]["filesystem_writes"], [])

    def test_token_only_comes_from_vault(self):
        for command in self.manifest["commands"]:
            self.assertNotIn("token", command["input_schema"])
            self.assertNotIn("api_key", command["input_schema"])

    def test_free_module(self):
        self.assertFalse(self.manifest["license_required"])

    def test_no_placeholder_publisher_key(self):
        publisher_pubkey = self.manifest.get("publisher_pubkey")
        if publisher_pubkey is None:
            return

        self.assertRegex(publisher_pubkey, r"^[0-9a-f]{64}$")
        self.assertNotEqual(publisher_pubkey, "0" * 64)


if __name__ == "__main__":
    unittest.main()
