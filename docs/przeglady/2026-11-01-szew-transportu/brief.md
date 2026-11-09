# Transport seam implementation: external review brief

**Implementation under review:** `claude/transport-seam-spec` at `8095f4f` (2026-11-01), compared with `origin/claude/transport-seam-spec` at `345ed73`. That range has 19 implementation commits; this brief follows in a separate commit. The implementation has not been accepted as D21 hardware evidence.

## Intended behavior

The station can use a numbered WICI-Link bearer over raw SX1262 radio frames, while the receiver can route replies over WICI-Link or Reticulum according to the authenticated inbound path. A station with no numbered network configuration continues to use the Reticulum bearer. There are no deployed installations or backward-compatibility requirements for the new numbered protocol.

WICI-Link v2 authenticates each hop with an eight-byte truncated HMAC and carries an encrypted, end-to-end envelope. DATA frames also carry a 64-byte Ed25519 signature over `"WICI K1 origin v1" || network_id || exact encrypted envelope`. A relay grants K1 priority only after verifying that signature against a provisioned station key for uplink or a receiver card for downlink. The maximum encrypted envelope in one DATA frame is 172 bytes; a 256-byte SA1 message fits in two envelopes.

The relay has four durable FRAM slots. K2 admission preserves two free slots for K1. A verified origin may occupy at most one pending K1 slot. Slot selection rotates, and the origin metadata is committed with the record CRC. A frame with no usable origin key or an invalid signature is treated as K2. The airtime journal caps transit plus BEACON airtime at 60% and BEACON airtime at 2%; when K1 waits, contended K2 uses a conservative 25% cap. HACK is sent only after durable admission at a relay or destination.

Station migration uses an authenticated encrypted 256 KiB snapshot. The source freezes radio and durable state before exporting; the target stages and verifies the import before activation. Identity, envelope counters, reservations, and replay windows move together. Receiver recovery blocks transmission after restoring an older SQLite copy until a safe counter boundary is established or new identities are issued.

## Review map

| Concern | Main files |
|---|---|
| Protocol and acceptance criteria | `docs/spec/transport.md`, `docs/spec/wici-link.md`, `docs/spec/usb-protocol.md` |
| Link encoding, signature, relay admission and airtime | `firmware/src/wici_link.cpp`, `wici_origin.cpp`, `wici_hop.cpp`, `wici_relay.cpp`, `wici_airtime.cpp` |
| Radio and root integration | `firmware/src/wici_radio.cpp`, `wici_gateway.cpp`, `wici_destination.cpp`, `main.cpp` |
| End-to-end encryption and replay safety | `firmware/src/envelope*.cpp`, `software/laptop/wici/envelope.py`, `software/laptop/wici/stanowisko/envelope_inbox.py` |
| Migration and recovery | `firmware/src/migration_*.cpp`, `software/laptop/wici/migration*.py`, `software/laptop/wici/stanowisko/nosnik.py` |
| Receiver bearer selection | `software/laptop/wici/stanowisko/bearers.py`, `przyjecie.py`, `wici_stos.py` |
| Preparation and key provisioning | `firmware/src/config.cpp`, `software/laptop/wici/configdoc.py`, `software/laptop/wici/ui/` |

## Questions for an independent reviewer

1. Can any station holding the shared link key claim K1, displace another verified origin, or obtain HACK before bytes are durable? Check malformed headers, missing keys, duplicate and conflicting envelopes, restart, and a full queue.
2. Are signature domain separation, sender/receiver binding, fragmentation, nonce reservation, replay windows, and key handling consistent between C++ and Python?
3. Does the migration freeze and target activation sequence prevent two devices from transmitting with the same identity or reusing a nonce after interruption, rollback, or an uncertain write?
4. Can a restored receiver database send with a stale counter or choose a bearer from unauthenticated or stale routing state?
5. Are the airtime and queue limits conservative under failed writes, retries, restarts, silent mode, and emergency broadcast? Is the 200 ms HACK deadline plausible when Ed25519 verification and FRAM admission occur before HACK?
6. Does the packaged receiver include the pinned `cryptography` dependency and work on supported Windows hosts? A Windows package test was not part of this session.

## Evidence and limits

The latest local checks passed: `bench-a` and `l0` PlatformIO builds; 108 native/firmware and numbered-bearer tests; 224 laptop/receiver integration tests (seven skipped); 48 reference-model tests; JavaScript syntax; repository verification (1,845 local links); and `git diff --check`. A native C++ signature matches Python Ed25519 byte for byte. The WICI-Link model estimates 50 request/RECEIVED exchanges through one relay at **12.29 minutes typical** and **13.06 minutes with the largest request**, assuming successful hops and no collisions. These are calculations, not radio measurements.

Two XIAO ESP32-S3 plus Wio SX1262 boards passed diagnostic radio tests at 100/100 frames in each direction and raw 19-, 44-, and 255-byte frame transfer. The formal D21 decision still requires two RAK4631 kits and the prototype: W10 under 15 minutes with 50/50 RECEIVED; 20/20 under hostile-node traffic in 30 minutes; HACK within 200 ms; emergency broadcast, cold start and power-loss trials; migration/nonce safety; and energy and RAM measurements. See `docs/spec/transport.md` under “Warunek przyjęcia”.

The working tree also contains unrelated, preexisting diagnostic edits and untracked artifacts. They are outside the review diff; review the committed branch range above.
