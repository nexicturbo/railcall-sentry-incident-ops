from __future__ import annotations

import unittest

from sentry_incident_ops.proof import ZERO, canonical_bytes, digest, safety_proof


class ProofTests(unittest.TestCase):
    def test_canonical_key_order(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_digest_is_deterministic(self):
        self.assertEqual(digest({"a": 1}), digest({"a": 1}))

    def test_digest_changes(self):
        self.assertNotEqual(digest({"a": 1}), digest({"a": 2}))

    def test_chain_links(self):
        proof = safety_proof("sentry.test", (("intent", {"a": 1}), ("outcome", {"b": 2})))
        self.assertEqual(proof["chain"][0]["previous"], ZERO)
        self.assertEqual(proof["chain"][1]["previous"], proof["chain"][0]["digest"])
        self.assertEqual(proof["root"], proof["chain"][-1]["digest"])

    def test_proof_does_not_embed_payload(self):
        proof = safety_proof("sentry.test", (("intent", {"token": "never-embed"}),))
        self.assertNotIn("never-embed", repr(proof))


if __name__ == "__main__":
    unittest.main()
