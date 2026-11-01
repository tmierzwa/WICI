# Transport seam review response

Status: software follow-up to `docs/transport-seam-review.md`, 2026-11-01. D21 acceptance is still pending.

| Review finding | Change |
|---|---|
| 1, relay liveness | Durable queue entries now expire after 30 minutes and leave a seen marker. A failed next hop no longer holds an origin slot forever. |
| 2, HACK deadline and K1 admission | A relay commits ordinary frames as K2 before HACK. Ed25519 verification normally runs later and is rechecked after restart. If two K2 slots are occupied, it verifies a signed K1 candidate, commits it into reserved space, and waits for a retry before HACK. It enforces one durable K1 slot per verified origin. |
| 3, receiver package | The package self-check accepts the pinned OpenSSL backend. A macOS arm64 package was built and imported. CI now builds Windows and both macOS targets. |
| 4, forced migration | Forced activate and abort commands are rejected. The two independent operator actions that could put the same sender identity on air were removed. |
| 6, replay amplification | The durable seen ring keys on the envelope identity and payload digest across hop sequence and MAC rewrites. It retains 224 entries for up to one hour. Repeated HACKs for queued or forwarded copies are limited to one per five seconds. The ring is bounded, so this is a traffic bound, not permanent replay prevention at relays. |
| 7, routing and hop source | Root epochs and each sender's BEACON fields are signed. Down routes are learned only after a valid origin signature. Numbered unicast DATA and HACK now require an 8-byte pairwise hop tag derived from the two neighbors' X25519 identities. The radio boundary verifies this before the relay or USB sees the frame, so a holder of only the shared link key cannot rewrite `l_src` or forge a neighbor HACK. Full route tables evict entries. |
| 8, parent recovery | A fresh signed BEACON reopens a failed planned or backup parent; the backup may have a worse rank than the previous route. Dynamic neighbor entries no longer displace configured parents. |
| 9, CI | UI text is generated from the canonical spec, simulator output is rebuilt, crypto sources are fetched for checks, migration vectors are included, and firmware path filters cover the native transport tests. |

Additional follow-up: durable counter, replay and fragment records now bind to a derived-key fingerprint; unreadable receiver snapshots fail closed; the USB export begin timeout covers the firmware's full image passes; Reticulum is tried when WICI returns no delivery and no operator override requires WICI; origin signatures use the MIT Crypto implementation directly; the package retains wheel metadata and SBOMs and includes OpenSSL's license text.

This follow-up also adds an offline receiver rekey procedure. After an old copy is restored, the outbound guard stays set while two duty officers stage a fresh private identity and receiver card. Activation verifies the staged card against the sealed identity and durable database marker; it requires operator confirmation that stations have the new card. Interrupted writes leave the guard set. Counter reuse under the old identity is therefore not authorized by recovery.

Verification: native hop-auth and relay checks cover a valid pairwise tag, a shared-key frame rewrite with an invalid hop tag, two occupied K2 slots, signed K1 admission, and HACK on retry. Receiver tests cover interrupted staging and activation. The stable full run passed 761 tests (59 skipped), and the reference suite passed 48 tests. Both `l0` and `bench-a` firmware images build; the simulator artifact was rebuilt and its freshness check passes. A macOS arm64 receiver package builds and imports the new rekey module. Two connected Wio SX1262/XIAO boards running the separate `pair-0.4` diagnostic exchanged 3/3 packets in each direction; this is a short radio check, not a WICI-Link protocol acceptance test.

Remaining gates:

1. A live multi-station receiver-card provisioning drill and the hostile-node test must exercise the new hop tags and K1 retry behavior on target hardware.
2. Backup receiver activation still needs a durable counter lifecycle. Torn migration barrier writes deliberately fail closed and need a recovery procedure; the real `BenchHost` migration flow still lacks a host harness.
3. The historical branch commits lack DCO signoffs. A new signoff cannot attest to another author's past commits; the original contributors must resolve the history.
4. D21 timing, W10 delivery, and power-loss acceptance still require the target RAK4631 and prototype hardware. Two Wio SX1262/XIAO boards alone do not cover those gates.
