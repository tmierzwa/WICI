# Transport seam review response

Status: software follow-up to `docs/transport-seam-review.md`, 2026-11-01. D21 acceptance is still pending.

| Review finding | Change |
|---|---|
| 1, relay liveness | Durable queue entries now expire after 30 minutes and leave a seen marker. A failed next hop no longer holds an origin slot forever. |
| 2, HACK deadline | A relay commits a frame as K2 before HACK. Ed25519 verification runs later, once per queue generation per boot; a valid result is cached and committed before K1 scheduling. Restart rechecks the signature in case provisioning changed. |
| 3, receiver package | The package self-check accepts the pinned OpenSSL backend. A macOS arm64 package was built and imported. CI now builds Windows and both macOS targets. |
| 4, forced migration | Forced activate and abort commands are rejected. The two independent operator actions that could put the same sender identity on air were removed. |
| 6, replay amplification | The durable seen ring keys on the envelope identity and payload digest across hop sequence and MAC rewrites. It retains 224 entries for up to one hour. Repeated HACKs for queued or forwarded copies are limited to one per five seconds. The ring is bounded, so this is a traffic bound, not permanent replay prevention at relays. |
| 7, routing | Root epochs and each sender's BEACON fields are signed. Down routes are learned only after a valid origin signature; full route tables evict entries. A holder of the shared link key can still spoof the link source of a captured, valid signed envelope and poison a down route. Pairwise hop authentication or an equivalent authenticated adjacency is needed to close that path. |
| 8, parent recovery | A fresh signed BEACON reopens a failed planned or backup parent; the backup may have a worse rank than the previous route. Dynamic neighbor entries no longer displace configured parents. |
| 9, CI | UI text is generated from the canonical spec, simulator output is rebuilt, crypto sources are fetched for checks, migration vectors are included, and firmware path filters cover the native transport tests. |

Additional follow-up: durable counter, replay and fragment records now bind to a derived-key fingerprint; unreadable receiver snapshots fail closed; the USB export begin timeout covers the firmware's full image passes; Reticulum is tried when WICI returns no delivery and no operator override requires WICI; origin signatures use the MIT Crypto implementation directly; the package retains wheel metadata and SBOMs and includes OpenSSL's license text.

Remaining gates:

1. Receiver recovery still blocks WICI replies after restoration from an old copy. It needs a proven upper counter boundary from intact state or a newly provisioned receiver identity on all stations. Clearing the guard without one of these would risk nonce reuse.
2. Deferred K1 verification can be starved while the two K2 admission slots are occupied. The shared link key also leaves hop-source spoofing possible. Both need a priority and hop-authentication design before the hostile-node acceptance test.
3. Backup receiver activation still needs a durable counter lifecycle. Torn migration barrier writes deliberately fail closed and need a recovery procedure; the real `BenchHost` migration flow still lacks a host harness.
4. The historical branch commits lack DCO signoffs. A new signoff cannot attest to another author's past commits; the original contributors must resolve the history.
5. D21 timing, W10 delivery, hostile-node, and power-loss acceptance still require the target RAK4631 and prototype hardware. Two Wio SX1262/XIAO boards alone do not cover those gates.
