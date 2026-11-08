# Transport seam review response

Status: follow-up to `docs/przeglady/2026-11-01-szew-transportu/review.md`, 2026-11-01, with the DATA signature decision of 2026-11-02 (below). D21 is not accepted; the bench trial on RAK4631 and the prototype decides it.

## Findings

| Finding | Change |
|---|---|
| 1, relay liveness | Queue slots expire after 30 minutes and leave a seen marker; a failed next hop no longer holds an origin slot. |
| 2, HACK deadline | Frames are committed as K2 before HACK; Ed25519 verification runs later and again after restart. With two K2 slots occupied, a signed K1 candidate is verified, stored in a reserved slot and acknowledged on the sender's retry. One durable K1 slot per verified origin. |
| 3, receiver package | The self-check accepts the pinned OpenSSL backend. CI builds and imports the package on Linux, Windows and both macOS targets. |
| 4, forced migration | Forced activate and forced abort are removed. |
| 5, receiver recovery | Offline rekey: after an old copy is restored the outbound guard stays set until two duty officers stage a new identity and receiver card; activation checks the card against the sealed identity and requires confirmation that stations have it. Interrupted writes keep the guard. |
| 6, replay amplification | The seen ring keys on envelope identity and payload digest, keeps 224 entries for up to one hour, and limits repeated HACKs to one per 5 s per envelope. It is bounded, so it limits traffic but is not permanent replay protection. |
| 7, routing and hop source | Root epochs and BEACON route fields are signed. Down-routes are learned only after a valid origin signature. Unicast DATA and HACK carry an 8 B pairwise hop tag from the neighbours' X25519 keys, checked before routing or USB. Full route tables evict entries. |
| 8, parent recovery | A fresh signed BEACON reopens a failed planned or backup parent, regardless of rank; dynamic neighbours no longer displace configured parents. |
| 9, CI | UI texts are generated from the spec; the simulator image is rebuilt; `checks.yml` fetches the pinned stack, so native envelope, WICI-Link and migration checks run in every PR. |
| 10, DCO | Not fixable here: a new sign-off cannot attest to other authors' commits. |

Also: counter, replay and fragment records bind to a key fingerprint; unreadable receiver snapshots fail closed; the export-begin timeout covers both image passes; Reticulum is tried when WICI reports no delivery and no operator override requires WICI; origin signatures call the MIT Crypto library directly; the package keeps wheel metadata, SBOMs and the OpenSSL licence.

## Airtime after the fixes

In v2, unicast DATA = 11 B header + envelope + 64 B origin signature + 8 B network MAC + 8 B hop tag, so 91 B plus the envelope (25 B overhead) and at most 164 B of envelope. v3 (2026-11-02) drops the signature: 27 B plus the envelope, at most 228 B (`firmware/src/wici_link.h`). HACK is 27 B, BEACON 156 B. Model: `wici_link` in `software/reference/obliczenia.py`, SF7/125 kHz, CR 4/5, preamble 24, 3 ms ramp per frame, relay channel time 13 × TX including HACKs; 95% hop success means 1.0525 transmissions per frame.

| 50 requests through one relay, minutes | buttons only (106 B) | typical (174 B) | largest (222 B) | largest, 95% hop success | largest, with read and decision |
|---|---|---|---|---|---|
| signature on every DATA (v2, replaced) | 8.97 | 13.36 | 14.14 | 14.88 | 22.57 |
| signature once per SA1 message (not implemented; no longer in the model) | 8.97 | 12.86 | 13.62 | 14.33 | 22.05 |
| hop tag only, K1 quota per neighbour (v3, implemented 2026-11-02) | 6.98 | 8.09 | 11.13 | 11.71 | 17.56 |

The v2 design met the W10 gate (<15 min) only with 0.12 min margin at 95% hop success, before collisions, CCA deferrals and a busy root. That is not a credible margin. Other budgets held for v2: mixed trial (55 revisions) 24.8 min of 60; hostile node (20 largest requests, one 255 B K2 frame before each relayed K1 frame) 11.1 min, 11.7 min at 95% and 19.4 min at 50% of 30; cold start of 50 stations 2.1 min of airtime, 5% of the TEST window, with 22% of it for the relay before the receiver. For v3 the model gives 19.3 min for the mixed trial, 10.4 min at 95% and 17.3 min at 50% for the hostile node, and 1.8 min for the cold start of 50 stations.

## Origin signature or hop tag

Keys come from USB-provisioned cards, and every station holds the shared network key, so one captured station leaks it.

- The hop tag stops a network-key holder from forging a neighbour's `l_src` or a HACK. A forged HACK makes the sender drop a frame it believes delivered, and SA1 retries only after 10 minutes. The origin signature cannot stop this; it covers neither HACK nor hop fields.
- The origin signature additionally stops a captured station from claiming K1 or redirecting down-routes under another station's number at relays two or more hops away. At its own parent, one K1 slot per authenticated neighbour gives the same bound as one slot per verified origin today.
- In the pilot plan (at most two hops to the receiver) every relay sees origins as direct neighbours, so the signature adds nothing that a per-neighbour K1 quota and down-routes learned only for the neighbour itself or stations the network plan places behind it do not give. Signing only K1 frames changes nothing, because all W10 traffic is K1.

Recommendation: keep the hop tag and the BEACON signatures, remove the origin signature from DATA, and add the per-neighbour K1 quota and plan-bound down-route learning. This restores 3.3 min (22%) of W10 margin at 95% hop success and removes Ed25519 verification from the relay.

**Decision, 2026-11-02: option D, implemented as WICI-Link v3.** DATA carries no origin signature; the envelope limit is 228 B and a typical REQUEST is one 226 B frame. A relay classifies a DATA frame as K1 when its envelope is addressed to or from an active receiver and its link source passed the hop tag, with at most one pending K1 slot per neighbour (K2 holds at most two of four slots). The deferred verification, the K2-then-upgrade path and re-verification after restart are removed; the first retry after a K1 admission still gets its HACK. A relay learns that station S is reached via neighbour N only if S is N or the configure document lists S in N's `priority_keys` entry under `behind`. The wire version and the link key label are v3, so v2 frames are refused. Residual risk: a captured station degrades traffic through its parent and down-routes to stations the plan places behind it, but cannot forge or block traffic at relays beyond its parent. If chains longer than the pilot's two hops are planned after T5, a signature can return as a K1 credential beyond the first hop.

## Verification

Native checks cover a valid pairwise tag, a shared-key rewrite with an invalid hop tag, two occupied K2 slots, signed K1 admission with HACK on retry, and interrupted receiver staging and activation. On 2026-11-01: the reference suite passes 49 tests; `python3 -m unittest discover -s tests` with the whole pinned stack passes 761 tests (60 skipped, each covered by a dedicated CI job); the publication job's run on Python 3.14 with only Crypto fetched has no skip for a missing compiler, cryptography or Unicode version; `tools/verify_repository.py --pull-request` and `reuse lint` pass. Earlier in this follow-up `l0` and `bench-a` built and a macOS arm64 receiver package built and imported the rekey module. Two Wio SX1262/XIAO boards exchanged 3/3 packets each way on the `pair-0.4` diagnostic; that is a radio check, not a WICI-Link acceptance test.

## Remaining gates

1. The bench trial on RAK4631 and the prototype: W10, the hostile-node test with hop tags and K1 retry, HACK within 200 ms, power loss, energy and RAM (`docs/spec/transport.md`, "Warunek przyjęcia"). Two Wio SX1262/XIAO boards passed only a short radio check.
2. ~~Backup receiver activation still needs a durable counter lifecycle, and the real `BenchHost` migration flow has no host harness.~~ Closed 2026-11-02. The backup package is single-use: `aktywuj-zapasowa` marks it used before the new medium exists, and every later activation starts with `env_send_guard`, released only by `nowa-tozsamosc` and `aktywuj-tozsamosc` (`tests.test_stanowisko.BackupActivationTest`). `tests/test_migration_host.py` drives two real bench-b station programs (the simulator's native build) through the USB protocol with the laptop coordinator: full migration, power loss after export, import and retire, a FRAM power cut after every byte of `activate`, and the abort paths (firmware.yml, `migration`, about a minute). bench-b has no WICI-Link radio, so the envelope counter bound is checked in the migrated FRAM, not on air; the counters' radio path stays with the bench trial. A torn barrier write now falls back to the last complete copy (second review).
3. DCO sign-offs for the historical branch commits must come from their authors.
4. ~~The decision on the DATA origin signature~~: decided 2026-11-02, option D (above).
