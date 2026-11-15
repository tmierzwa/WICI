#!/usr/bin/env python3
"""Envelope counters, nonce reuse and floods in a monitor.py JSONL capture (prób 12, 14 i 16).

The WICI envelope header is plaintext at byte 11 of a DATA frame: kind (1 B), src, dst (u16 BE), ctr (u32 BE);
the nonce is src ‖ dst ‖ kind ‖ 0 ‖ ctr (docs/spec/transport.md). A nonce repeats when one (src, dst, kind, ctr)
carries two different envelopes. Retries and forwarding copy the same envelope bytes, so they are not reuse.

--mark T (host time, Unix seconds; repeatable) splits the capture at a transfer or restart of the station --src.
One counter serves all kinds of one (src, dst) pair (parts 1/2 and 2/2 share a value). For every pair the report
gives the largest ctr seen before the mark and the ctr of the first envelope first seen after it; copies of older
envelopes (forwarding, retries) are skipped. That ctr must be a multiple of 64 and larger than every earlier one
(reservation in blocks of 64, envelope_counter.h).

Floods are DATA with l_dst 0xFFFF; every node must send each envelope at most once (one link seq per l_src).
"""

import argparse
import json
import sys
from collections import defaultdict

HEADER, MAC, PAIR = 11, 8, 8
BROADCAST = 0xFFFF
BLOCK = 64


def envelopes(lines):
    """Yield (host_ts, v3 header, kind, src, dst, ctr, envelope bytes) for each authenticated DATA frame."""
    for line in lines:
        record = json.loads(line)
        v3 = record.get("v3")
        if not v3 or v3.get("type") != 0 or record.get("mac_ok") is False or not record.get("crc", True):
            continue
        raw = bytes.fromhex(record["hex"])
        end = len(raw) - MAC - (0 if v3["l_dst"] == BROADCAST else PAIR)
        body = raw[HEADER:end]
        if len(body) < 7:
            continue
        kind, src, dst, ctr = body[0], int.from_bytes(body[1:3], "big"), int.from_bytes(body[3:5], "big"), \
            int.from_bytes(body[5:9], "big")
        yield record["host_ts"], v3, kind, src, dst, ctr, body


def analyse(lines, marks=(), src_filter=None):
    seen = defaultdict(set)          # (src, dst, kind, ctr) -> envelope bodies
    first_seen = {}                  # envelope body -> (ts, src, dst, ctr)
    floods = defaultdict(set)        # ((src, dst, kind, ctr), l_src) -> link seqs
    for ts, v3, kind, src, dst, ctr, body in envelopes(lines):
        seen[(src, dst, kind, ctr)].add(body)
        first_seen.setdefault(body, (ts, src, dst, ctr))
        if v3["l_dst"] == BROADCAST:
            floods[((src, dst, kind, ctr), v3["l_src"])].add(v3["seq"])
    reuse = sorted(key for key, bodies in seen.items() if len(bodies) > 1)
    repeated_floods = sorted((key, src, sorted(seqs)) for (key, src), seqs in floods.items() if len(seqs) > 1)
    pairs = defaultdict(list)        # (src, dst) -> [(first ts, ctr)] of distinct envelopes
    for ts, src, dst, ctr in first_seen.values():
        if src_filter is None or src == src_filter:
            pairs[(src, dst)].append((ts, ctr))
    boundaries = []
    for mark in sorted(marks):
        for key, values in sorted(pairs.items()):
            before = [c for t, c in values if t < mark]
            after = sorted((t, c) for t, c in values if t >= mark)
            if not before or not after:
                continue
            first = after[0][1]
            boundaries.append({"mark": mark, "src": key[0], "dst": key[1], "last_before": max(before),
                               "first_after": first, "ok": first > max(before) and first % BLOCK == 0})
    return {
        "envelopes": len(seen),
        "nonce_reuse": [{"src": s, "dst": d, "kind": k, "ctr": c} for s, d, k, c in reuse],
        "flood_envelopes": len({key for key, _ in floods}),
        "flood_senders": len(floods),
        "repeated_floods": [{"src": k[0], "dst": k[1], "kind": k[2], "ctr": k[3], "l_src": s, "seqs": q}
                            for k, s, q in repeated_floods],
        "boundaries": boundaries,
        "ok": not reuse and not repeated_floods and all(b["ok"] for b in boundaries),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", help="JSONL z tools/monitor.py")
    parser.add_argument("--mark", type=float, action="append", default=[],
                        help="chwila przeniesienia albo restartu (host_ts, s); można podać wiele razy")
    parser.add_argument("--src", type=int, help="numer stacji, której dotyczą chwile --mark")
    args = parser.parse_args(argv)
    with open(args.capture, encoding="utf-8") as handle:
        result = analyse(handle, args.mark, args.src)
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
