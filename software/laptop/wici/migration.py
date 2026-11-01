# SPDX-License-Identifier: MIT
"""Resumable two-station USB migration coordinator.

The stations enforce the radio lock and confirmations. This client never
unlocks a station on an error; rerunning it reads both durable states first.
"""

import argparse
import hashlib
import json

from . import serialport
from .usbproto import Link, ProtocolError

PACKAGE_SIZE = 101 + 512 * (512 + 16)
SNAPSHOT_SIZE = 256 * 1024
HEADER_SIZE = 101


def _hex(value, size, field):
    if not isinstance(value, str) or len(value) != size * 2 or any(c not in "0123456789abcdef" for c in value):
        raise ProtocolError(f"invalid {field}")
    return bytes.fromhex(value)


def _status(link):
    reply = link.request("migrate", step="status")
    if reply.get("type") != "ok" or not isinstance(reply.get("migration"), str):
        raise ProtocolError("invalid migration status")
    return reply


def _confirmation(status, field):
    return _hex(status.get("confirm"), 32, field).hex()


def _header(package, mid):
    raw = package[:HEADER_SIZE]
    if len(raw) != HEADER_SIZE or raw[0] != 1 or raw[1:17] != mid or \
            int.from_bytes(raw[97:101], "big") != SNAPSHOT_SIZE:
        raise ProtocolError("invalid encrypted package header")
    return {"ephemeral_public": raw[33:65], "package_hash": raw[65:97]}


def migrate(source, target):
    """Complete or resume normal migration; return identifiers and digests.

    Forced recovery and abort are separate operator actions. A failed step
    leaves the source locked, the target locked, or both; rerun this function.
    """
    source_state, target_state = _status(source), _status(target)
    source_phase, target_phase = source_state["migration"], target_state["migration"]
    if source_phase not in ("none", "export", "retired"):
        raise ProtocolError(f"source migration phase {source_phase}")
    if target_phase == "none":
        if source_phase != "none":
            raise ProtocolError("target is empty while source is locked; inspect both stations")
    elif target_phase not in ("receiving", "importing", "imported"):
        raise ProtocolError(f"target migration phase {target_phase}")
    if source_phase == "none" and target_phase in ("importing", "imported"):
        raise ProtocolError("target has an import but source has no matching export")
    if source_phase == "retired" and target_phase != "imported":
        raise ProtocolError("source retired before target reported imported")

    key_reply = target.request("migrate", step="receive_key")
    mid = _hex(key_reply.get("mid"), 16, "mid")
    target_key = _hex(key_reply.get("key"), 32, "target key")
    fingerprint = _hex(key_reply.get("fingerprint"), 8, "target fingerprint")
    if fingerprint != hashlib.sha256(mid + target_key).digest()[:8]:
        raise ProtocolError("target fingerprint mismatch")
    mid_hex = mid.hex()
    if source_phase != "none" and source_state.get("mid") != mid_hex:
        raise ProtocolError("source is locked to another migration")
    if target_phase != "none" and target_state.get("mid") != mid_hex:
        raise ProtocolError("target migration ID changed")

    package = None
    if source_phase != "retired" and target_phase != "imported":
        package = source.read_transfer("export", mid=mid_hex, target_key=target_key.hex())
        if len(package) != PACKAGE_SIZE:
            raise ProtocolError("wrong encrypted package size")
        header = _header(package, mid)
        source_state = _status(source)
        if source_state["migration"] != "export" or source_state.get("mid") != mid_hex or \
                source_state.get("eph") != header["ephemeral_public"].hex() or \
                source_state.get("package") != header["package_hash"].hex():
            raise ProtocolError("source export changed")
    if target_phase != "imported":
        if package is None:
            raise ProtocolError("no package for target import")
        imported = target.write_transfer("import", package, mid=mid_hex)
        imported_confirm = _hex(imported.get("confirm"), 32, "imported confirmation").hex()
    else:
        imported_confirm = _confirmation(target_state, "imported confirmation")

    if source_phase != "retired":
        retired = source.request("migrate", timeout=60, step="retire", mid=mid_hex, confirm=imported_confirm)
        retired_confirm = _hex(retired.get("confirm"), 32, "retired confirmation").hex()
    else:
        retired_confirm = _confirmation(source_state, "retired confirmation")
    activated = target.request("migrate", step="activate", mid=mid_hex, confirm=retired_confirm)
    if activated.get("type") != "ok":
        raise ProtocolError("target activation failed")
    return {"mid": mid_hex, "fingerprint": fingerprint.hex(),
            "package_sha256": hashlib.sha256(package).hexdigest() if package is not None else None,
            "activated": True}


def _open(name):
    link = Link(serialport.open_port(name))
    if not link.wait_hello():
        link.close()
        raise ProtocolError(f"no station hello on {name}")
    return link


def main(argv=None):
    parser = argparse.ArgumentParser(description="Move one WICI station to a prepared empty station")
    parser.add_argument("--source-port", required=True, help="source station USB data port")
    parser.add_argument("--target-port", required=True, help="target station USB data port")
    args = parser.parse_args(argv)
    if args.source_port == args.target_port:
        parser.error("source and target ports must differ")
    source = _open(args.source_port)
    try:
        target = _open(args.target_port)
        try:
            print(json.dumps(migrate(source, target), sort_keys=True))
        finally:
            target.close()
    finally:
        source.close()


if __name__ == "__main__":
    main()
