# Transport seam implementation: independent review

**Scope:** `claude/transport-seam-spec`, `345ed73..8095f4f` (19 implementation commits) plus the brief (`53fb953`) and merge (`84312fa`), reviewed 2026-11-01 against `docs/transport-seam-review-brief.md`, `docs/spec/transport.md`, `docs/spec/wici-link.md` and `docs/spec/usb-protocol.md`.
**Method:** four independent review passes (link/relay/airtime, envelope cryptography, migration/recovery, evidence and hygiene) and one architecture pass. Reviewers built and ran the native checks with clang++ and sanitizers against the pinned `attermann/Crypto@984dc89`, wrote adversarial harnesses (about 2 100 extra C++/Python vectors, relay and routing attack tests, an Ed25519 cost benchmark), and reran the Python suites. PlatformIO images could not be built here: the PlatformIO registry is blocked by this environment's proxy.
Letters in parentheses after findings name the review pass: A link/relay/airtime, B envelope cryptography, C migration/recovery, D evidence and hygiene, E architecture. Adversarial harnesses and per-pass notes are not part of this commit.

## Verdict

Not ready for the D21 bench trial. The cryptographic core is sound: envelope encryption, key derivation, replay windows and origin signatures match byte for byte between C++ and Python, and HACK is never sent before bytes are durable. The relay and routing layer, however, has liveness failures that occur without any attacker, several attacks open to any holder of the shared link key (and two to a passive listener), and a HACK deadline that the RAK4631 cannot meet with the current signature path. The receiver package does not build as committed and the CI test suite has three regressions. The Ed25519 signature on every DATA frame also costs most of the airtime gain that motivated D21.

## Blocking findings

| # | Severity | Area | Finding | Evidence |
|---|---|---|---|---|
| 1 | Critical | Relay | Relay queue items never expire. After 3 failed hops the frame stays (`wici_hop.cpp:206`), and each verified origin may hold only one K1 slot (`wici_relay.cpp:158`). One unacknowledged frame therefore blocks that origin at the relay for good. For downlink the origin is the receiver, so all receiver→station traffic through that relay stops, including emergency floods. Triggers without an attacker: a down-route to a dead neighbour (routes are never forgotten), or a destination refusing an authenticated envelope outside its replay window (`station.cpp:733`). | Reproduced in native harness (A) |
| 2 | Critical | Timing | Ed25519 verification sits on the synchronous HACK path, before deduplication, and `prepare()` re-verifies via `priority()` up to twice per slot on every loop pass (`wici_hop.cpp:58,117,140`). Measured cost of the pinned portable implementation is about 9.9 M instructions: ≈190–400 ms on nRF52840, ≈50–120 ms on ESP32-S3. `measure.cpp:360` requires the HACK to *finish* within 200 ms, leaving ≈109 ms. On RAK4631 every K1-eligible relayed uplink misses HACK. | Benchmark and call count (A, D) |
| 3 | Critical | Packaging | Receiver package build fails: pinned Reticulum selects the OpenSSL backend when `cryptography` is importable, but `build_stanowisko.py:178-181` asserts the internal backend (`AssertionError: openssl, PyCA 48.0.1`). The CI `stanowisko` job will fail. No CI job builds or runs the package on Windows or macOS, so brief Q6 is answered "no". | Reproduced (D) |
| 4 | High | Migration | Forced activate on the target (`main.cpp:971-1002`) and forced abort on the source (`main.cpp:1053-1093`, `usbproto.cpp:479-493`) are independent operator actions. Used together they put two stations on air with the same identity and counters, i.e. ChaCha20-Poly1305 nonce reuse. A target left in IMPORTED can also be force-activated much later with a stale snapshot. | Traced (C) |
| 5 | High | Receiver | Recovery permanently disables WICI-Link replies: `env_send_guard` (`przyjecie.py:71-74,272`) is never cleared and neither remedy in `transport.md:70` (safe counter boundary, new identities) is implemented. After a planned spare-computer or `kopie` recovery, every reply to a numbered station fails and retries forever. | Traced (C) |
| 6 | High | Relay | Keyless replay. A captured signed DATA frame replayed after the 120 s seen window is admitted as K1, HACKed and forwarded again; a link-key holder can re-MAC it at any time. Each duplicate also triggers a fresh HACK adding ≈0.85 s silence debt (up to 10 s), so ≈1 replay/s keeps a relay from ever forwarding. Two crafted frames with the same `l_src`/`seq` make `finishForwarded` fail for every slot for 120 s. | Partly reproduced (A) |
| 7 | High | Routing | Downlink sinkhole: down-routes are learned from unsigned frames; one forged frame redirects a station's downlink, and the 256-entry table never evicts. BEACON `epoch` is unauthenticated: one forged high epoch makes stations ignore the genuine root until it restarts tens of thousands of times (a replaced or wiped root does the same). Sixteen forged neighbours evict the planned parent. | Reproduced (A) |
| 8 | High | Routing | Parent loss is permanent within an epoch: after 3 failures to the planned parent the station has no parent; planned-parent beacons never restore it (12 h test), and the backup is ineligible if its rank is not below the station's best rank. Spec requires return to the planned parent and own-frame failover to the backup. | Reproduced (A) |
| 9 | High | CI | `python3 -m unittest discover -s tests` (the CI command): 759 tests, 3 failures, all introduced by the branch: hand-edited `ui_texts.h` (5 migration texts absent from `oprogramowanie.md`, missing Polish diacritics) and a stale committed simulator image (`build.json`, `*.mjs`, not rebuilt since `b4f0a12`). The brief's "108 + 224" counts are subsets. | Reproduced (D) |
| 10 | High | Process | DCO: none of the 21 commits has `Signed-off-by`; `tools/check_dco.py` fails. | Reproduced (D) |

## Other findings

**Medium**
- Counters, replay windows and fragment slots are bound to network and station numbers, not keys (`envelope_counter.cpp:55-58`, `envelope_replay.cpp:61-66`, `envelope_parts.cpp`). After renumbering, the numbered radio fails at every boot; after issuing a new receiver identity under the same number (the spec's own recovery remedy) stations reject its counters and downlink stops. Bind records to a key fingerprint. (B)
- Backup receiver identity has no counter boundary: each activation starts at 0 (`envelope_sender.py:49`); two activations reuse nonces. Not reachable yet (`open_backup` has no caller); fix in that flow. (B, C)
- Reticulum-only stations can be starved: default bearer is `wici` with no fallback (`bearers.py:57-58`); a trusted station not on the numbered network that never sent anything is never tried on Reticulum. Replayed genuine messages move the reply route, and routes never expire (`envelope_inbox.py:96-97`, `przyjecie.py:437-475`). (C)
- An interrupted barrier write leaves the source "corrupt" (`migration_state.cpp:92-93`) with ZNISZCZ DANE as the only exit. `nosnik.load` silently falls back to the older snapshot (`nosnik.py:137-143`), which can roll back counter reservations. `xfer_begin export` resume uses a 3 s timeout while firmware makes two full image passes (`usbproto.py:191`). The real `BenchHost::migration*` code has no host test. (C)
- Unsigned frame with the same envelope id blocks the genuine signed one; all downlink from one receiver is serialised to one frame per relay; floods are classed K1 (spec: K2) and signed emergency floods are dropped while a receiver frame is pending; own TTL is hard-coded to 7 (`wici_radio.cpp:206`); BEACON after parent/rank change and loop detection by envelope id are missing. (A)
- CI gaps: `checks.yml` never fetches the pinned stack, so crypto-dependent native tests silently skip; migration vectors run in no CI job; `firmware.yml` path filter misses `tests/native/{envelope,wici,migration}_*`. (B, D)
- Licences: `cryptography`, `cffi`, `pycparser` and the OpenSSL bundled in the wheel are missing from `LICENSE.md` and D09; the package drops the wheel's SBOM. (D)
- Licence goal of D21 not met: `wici_origin.cpp:6` and `wici_radio.cpp:6` include `identity.h` from `lib/reticulum_core` (Reticulum License) and call `rnscore::sign/validate`. The underlying Ed25519 is rweather Crypto (MIT) and can be called directly; a build without `lib/reticulum_core` is needed before claiming an MIT-only station. (E)
- Stale documents: `usb-protocol.md:3` says migration is unsupported; the D21 row in chapter 08 still quotes 7.3 min and one 218 B frame; `wici-link.md:129` claims 192 B FRAM free, constants leave 64 B; `firmware/README.md` FRAM map lacks the WICI structures. (D)

**Low**
- K1 signing keys are entered by hand and weak (small-order) Ed25519 keys are accepted; with the identity point as key a forged signature verifies, so one bad entry gives any link-key holder K1 for that station. Reject small-order keys at provisioning. (B)
- C++ keeps one pending fragment per receiver, Python four per sender; they differ on a whole message over a pending fragment with the same counter and on clock regressions. (B)
- One identity key serves Reticulum, envelope ECDH and origin signatures; domain separation holds, separate keys advisable in v2. (B, E)
- Blank counter slots restart at 0 although the identity exists; damaged COMMIT byte silently uses the older slot (`envelope_counter.cpp:55`, `wici_seq.cpp:45`). (B, C)
- TEST envelopes are rejected by both receivers while `wici-link.md` says routes are learned from the first TEST. (B)
- Target does not authenticate which source built the package; first fragment purged after 120 s although already HACKed; misleading error after a lost `activate` reply. (C)
- `manifest.json` changed in the PR (CONTRIBUTING.md:46); `usb-protocol.md` breaks the Polish filename convention; `wici_link.h:2` still says v1 and the raw radio evidence used v1 frames; `wici_route.cpp` fails `g++ -Werror=class-memaccess`. (A, D)

## Answers to the brief's questions

1. **K1 claim, displacement, early HACK.** No K1 without a valid signature; signature domain and key selection are correct; no HACK before durable storage. But replays obtain K1 (finding 6), a stuck frame permanently holds an origin's slot (1), and down-routes and epochs can be forged (7).
2. **C++/Python consistency.** Yes, byte for byte, including KDF, nonce, AAD, fragmentation, replay decisions and Ed25519. Issues are in record binding (counters to numbers, not keys) and fragment-policy differences, not in cryptography.
3. **Migration.** Without forced steps, every crash, power-loss and USB-disconnect point leaves at most one transmitting station and no nonce reuse. Forced activate plus forced abort breaks this (4).
4. **Restored receiver.** No stale-counter send: recovery mode and `env_send_guard` gate every path. But the guard is never lifted (5), replays can move the reply bearer, and Reticulum-only stations can be starved.
5. **Limits and HACK deadline.** Airtime and debt accounting are conservative (charged to FRAM before TX, failures keep the charge, silence blocks HACK/BEACON/relay). HACK count is unbounded under replay (6). The 200 ms deadline is not achievable on nRF52840 with the current verification path (2).
6. **Packaged receiver.** Wheels are complete and hash-pinned for all four targets, nothing downloads at runtime, but the build fails (3) and no Windows or macOS package job exists.

## Design observation: the signature costs the airtime gain

The 64-byte Ed25519 origin signature on every DATA frame lowers the per-frame envelope limit to 172 B, so a typical REQUEST becomes two 195 B frames. W10 rises from ≈7.3 min (unsigned draft) to 12.29 min typical and 13.06 min for the largest request (reproduced independently), leaving 14.8–22% margin under the 15 min gate before collisions and retries; at the spec's 95% hop success the largest case is ≈13.9 min. With "read" and decision, ≈20 min (not yet recalculated in the spec). It also doubles HACKs and signature checks per message and causes finding 2.

Alternatives worth evaluating before hardware:
- **Hop-pairwise MAC instead of a signature.** Each station shares an X25519-derived key with its planned parent and backup (public keys already on the cards). A relay classifies K1 for frames from an authenticated neighbour and applies per-neighbour quotas. 8–16 B instead of 64 B puts a typical REQUEST back in one frame (≈7.7 min) and costs microseconds instead of 100+ ms. A compromised relay can still prioritise its own traffic, which the current design also allows (one slot).
- **One signature per SA1 message** (part 1 signs a hash of both ciphertexts) instead of per fragment.
- If signatures stay: verify off the HACK path (HACK on durable admission as K2, upgrade to K1 after asynchronous verification), cache the verification result with the slot, and use a faster Ed25519 (e.g. Monocypher or hardware-assisted).

## Recommended order of work

1. Fix findings 1, 2, 6, 7, 8 in relay and routing: slot expiry and eviction, verification off the HACK path with caching, duplicate HACK rate limit, authenticated down-route learning (only from signed or envelope-verified frames), signed root epoch, planned-parent recovery. Add the adversarial harnesses from review A as permanent native checks.
2. Decide signature vs hop-pairwise MAC (design observation) before more code depends on it.
3. Fix 3, 9 and 10 so CI is green; add Windows and macOS package jobs and the pinned stack to `checks.yml`.
4. Fix 4 and 5 (forced migration steps, receiver recovery boundary) and bind counters/windows to key fingerprints.
5. Split migration and the USB spec rename into separate PRs; update the stale documents; move implementation narratives out of `wici-link.md` into firmware documentation.
6. Then the bench trial on RAK4631, with a measured per-MCU HACK timing budget as its first item.

## Second review, 2026-11-02

**Scope:** the branch after the authors' follow-up (`32d05cb`, `c2db2c1`), reviewed again in four areas (link layer and routing; envelope and keys; migration, USB protocol and receiver; concept, model, CI and documentation), with fixes made in this pass. Reviewers rebuilt the native checks with clang++ and g++ and sanitizers against the pinned stack, added adversarial checks, and reran every Python suite. PlatformIO images and the simulator image could not be built here (registry and Emscripten unavailable).

**Previous blocking findings.** Findings 1, 2 and 4–8 are fixed and covered by tests. Finding 3 is fixed for the Linux package built here; the Windows and macOS packages are built only in CI. Finding 9 is fixed except that the firmware changes in this pass make the committed simulator image stale again (below). Finding 10 (DCO) remains with the commit authors. The follow-up's claims were checked rather than trusted, and three of its fixes were incomplete:

| Problem found in this pass | Severity | Fix |
|---|---|---|
| The raw radio path accepted only the old 19 B HACK, while every real HACK is 27 B with the hop tag; the host harness used the stale frame. No HACK could have been sent on hardware. | Critical | `measure.cpp` accepts the tagged v2 HACK and refuses an untagged one; the host test uses real frames. |
| Re-provisioning (new network card) left the `seq`, route, flood, airtime and relay records refusing to start until ZNISZCZ DANE. | High | Each record type handles a foreign binding: reservations carry over, foreign entries are skipped, unauthenticable queue items are retired without a second send. |
| A K1 frame admitted without HACK could have its sender's retry swallowed by the 5 s repeat-HACK limit. | High | The first retry after K1 admission always gets its HACK. |
| A torn migration barrier write forced ZNISZCZ DANE and lost the identity. | High | A complete body with an unset commit byte is used, a torn one falls back to the other copy; real damage still blocks. |
| A replaced or wiped root restarts its epoch count and was ignored by every station. | High | An older epoch is accepted after 90 min without the current one. |
| The receiver keyed replay windows and fragments by numbers only; a station re-provisioned under the same number would never be acknowledged. A whole message was admitted over a pending fragment with the same counter, unlike the station. | Medium | Receiver tables are bound to the pair key; the whole-over-fragment case is rejected as on the station. |
| A damaged COMMIT byte fell back silently to the older copy (envelope counter, `seq`), allowing a repeated nonce; a blank counter area restarted at 0 although an identity existed. | Medium | One shared fail-closed FRAM record codec (`fram_record.h`); starting counter records are written when the identity is first saved, and a blank area is refused afterwards. |
| The hop key was an HMAC of the envelope encryption key under the envelope label. | Medium | Separate HKDF derivation from the X25519 secret with its own salt and labels; all-zero secrets refused; keys wiped on failure. |
| Small-order X25519 and Ed25519 keys were accepted in configure documents. | Medium | Refused on the station and in the laptop's preparation check from one list. |
| Floods were classed K1 and made relays verify signatures for any network-key holder. | Medium | Floods are K2 with no signature work. |
| Own frames never failed over to the backup parent; the hop limit was hard-coded to 7 on stations and on the receiver. | Medium | Backup failover; `network.ttl` (1–15) on stations and `--ttl` on the receiver. |
| The laptop had no migration withdraw path, a resumed run skipped an interrupted retire, receiver snapshots were rewritten in place, replays could move the reply route, and the recovery guard blocked the Reticulum fallback. | Medium | `--migrate-abort`; retire always resent; snapshots via temp file, fsync and rename; only fresh revisions move the route; Reticulum is tried when WICI has no delivery. |
| A target abort without `eph` deleted the transfer key, so a source that had already exported stayed locked. | Medium | The key is kept until the next `receive_key` or export. |
| Dead or duplicated code: two FRAM record codecs, an unused C++ `Bearer` contract, duplicated HACK/BEACON builders and radio interfaces, unused migration helpers, a `forced` parameter that could never be true, SA1 type checks repeated after the codec. | Low | Removed or merged; the transport spec now describes the seam as built. |
| CI repeated the long firmware suites in the publication job and could skip native checks silently. | Low | The publication job fetches only Crypto, runs on Python 3.14 and fails on any skip caused by a missing compiler, library or Unicode version. |

**Conceptual result.** With the 8 B hop tag added, every unicast DATA carries 91 B of link overhead. W10 for the largest request is 14.14 min without loss and 14.88 min at 95% hop success, leaving 0.12 min under the 15 min gate before collisions and deferrals. The hop tag is necessary: only it stops a network-key holder from forging `l_src` or a HACK. The origin signature on DATA adds protection only at relays two or more hops from the origin; with a per-neighbour K1 quota and down-routes bound to the network plan, dropping it gives 11.71 min (22% margin) and takes Ed25519 off the relay. This is a protocol decision and is recorded as open in the D21 row of chapter 08; it is not changed in this branch. *Note, 2026-11-02:* decided as option D and implemented as WICI-Link v3 (`docs/transport-seam-review-response.md`, "Origin signature or hop tag").

**Remaining before the bench trial.** Rebuild and commit the simulator image (`python3 software/simulator/build.py`, Emscripten 3.1.74): `tests.test_simulator.test_committed_build_is_current` fails until then. Build `bench-a` and `l0` with PlatformIO. ~~Decide the DATA signature~~ (decided 2026-11-02, option D). Backup receiver activation still lacks a counter lifecycle; the real `BenchHost` migration code still has no host harness. DCO sign-offs remain with the commit authors.
