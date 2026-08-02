"""Deterministic, secret-free hash chains for action safety evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


SCHEME = "railcall-sentry-safety-proof.v1"
ZERO = "0" * 64


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def safety_proof(command: str, phases: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    previous = ZERO
    chain: list[dict[str, str]] = []
    for phase, payload in phases:
        entry = {
            "scheme": SCHEME,
            "command": command,
            "phase": phase,
            "previous": previous,
            "payload_digest": digest(payload),
        }
        current = digest(entry)
        chain.append({"phase": phase, "previous": previous, "digest": current})
        previous = current
    return {"scheme": SCHEME, "command": command, "chain": chain, "root": previous}
