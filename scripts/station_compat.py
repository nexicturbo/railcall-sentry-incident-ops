#!/usr/bin/env python3
"""Load this module under the capability gate shipped in a RailCall bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tarfile


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _member(archive: tarfile.TarFile, suffix: str):
    for member in archive.getmembers():
        if member.name.replace("\\", "/").endswith(suffix):
            return member
    raise RuntimeError(f"RailCall bundle is missing {suffix}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=pathlib.Path)
    parser.add_argument("--expected-sha256", default="")
    args = parser.parse_args()

    bundle_bytes = args.bundle.read_bytes()
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    if args.expected_sha256 and bundle_sha.lower() != args.expected_sha256.lower():
        raise RuntimeError("RailCall bundle SHA-256 mismatch")

    with tarfile.open(args.bundle, "r:gz") as archive:
        sandbox_member = _member(archive, "workbench/module_sandbox.py")
        version_member = _member(archive, "workbench/STATION_VERSION.json")
        sandbox_source = archive.extractfile(sandbox_member).read()
        version = json.loads(archive.extractfile(version_member).read().decode("utf-8"))

    sandbox_ns = {"__name__": "railcall_module_sandbox_probe"}
    exec(compile(sandbox_source, "module_sandbox.py", "exec"), sandbox_ns)
    manifest = json.loads((ROOT / "module.json").read_text(encoding="utf-8"))
    handler_path = ROOT / "handlers" / "handler.py"
    handler_bytes = handler_path.read_bytes()
    handler_ns = {
        "__name__": "railcall_module_sentry_incident_ops_probe",
        "__file__": str(handler_path),
        "__rc_helpers__": {"vault_get": lambda _provider: {"SENTRY_AUTH_TOKEN": "probe-only"}},
    }
    summary = sandbox_ns["install_restrictions"](
        handler_ns, manifest["requires"], slug=manifest["id"]
    )
    sys.path.insert(0, str(ROOT))
    try:
        exec(compile(handler_bytes, str(handler_path), "exec"), handler_ns)
    finally:
        sys.path.remove(str(ROOT))

    missing = []
    for command in manifest["commands"]:
        function_name = command["id"].replace(".", "_").replace("-", "_")
        if not callable(handler_ns.get(function_name)):
            missing.append(function_name)
    if missing:
        raise RuntimeError(f"handlers missing after station-style exec: {missing}")

    # Prove the current station's network gate refuses an undeclared origin.
    try:
        import urllib.request

        urllib.request.urlopen("https://example.invalid/", timeout=1)
    except sandbox_ns["SandboxViolation"]:
        blocked = True
    else:
        blocked = False
    if not blocked:
        raise RuntimeError("RailCall sandbox did not block an undeclared origin")

    print(
        json.dumps(
            {
                "ok": True,
                "bundle_sha256": bundle_sha,
                "station_version": version,
                "manifest_version": manifest["manifest_version"],
                "commands_loaded": len(manifest["commands"]),
                "sandbox": summary,
                "undeclared_origin_blocked": blocked,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
