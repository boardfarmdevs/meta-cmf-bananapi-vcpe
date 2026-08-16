# EasyMesh — review TODO

Action list from an external read-only review of the repo (2026-08-13). Ordered
by the reviewer's priority. Each item: the problem, why it matters, the fix
direction, and status. The review's headline: the EasyMesh implementation is
**farther along than the "still converging" docs suggest** — the biggest
remaining weakness is now **deployment identity ownership**, then converting the
old hwsim 2-band/WPA2 assumptions into **capability-driven** behaviour so the
newly-proven Linux-7.0 6 GHz path can reach EasyMesh.

> **Progress (2026-08-12):** all eight items have code/doc changes landed. Doc (#6)
> and tooling (#5) are complete. The seven recipe/patch changes (#1, #2, #3, #4, #7,
> #8) are **pending a rebuild** to validate patch application + compilation, and #1
> additionally needs a two-cycle redeploy behavioural test. Two follow-ups remain
> open by nature (need a running 7.0 capable build): the embedded-libhostap-2.11
> 6 GHz SAE-H2E acceptance gate (#3) and full MLO per-link runtime logic (#7).
>
> **Update:** both images rebuilt clean (broadband + ap, after a per-build-dir
> `cleansstate` of ccsp-one-wifi — its patches are hand-applied so a content change
> needs a clean unpack). #1 additionally **validated live on rev150** (see its entry).

## P1

### 1. Redeploy identity is not atomic — the Issue-B mechanism still exists
`bpi.sh` documents the invariant (normal redeploy preserves identity; `-F` makes
a fresh `{AL-MAC, RUID-set}`) but does **not** guarantee it. The extender AL-MAC
is derived (EasyMesh bbappend) from the moved-in hwsim radio's `wlan0` MAC, and
`hwsim_attach_radios()` picks the *next free* phy — there is no persistent
container→phy mapping. So:
- normal redeploy can still give **new AL-MAC (new phy) + old RUIDs (`/nvram`)** =
  exactly the Issue-B mixed identity;
- `-F` has the mirror weakness: wipe `/nvram` (new RUIDs) but the allocator may
  hand back the **same** phy = old AL-MAC + new RUIDs.

**Fix direction:** make identity ownership explicit and atomic —
*same logical node* → preserve AL-MAC **and** RUID set; *replacement node* →
regenerate both. Never let pool allocation pick identity accidentally. Either
**pin/persist the hwsim radio assignment per logical node**, or **decouple the
AL-MAC from the currently-allocated phy** (e.g. derive it from the stable
container name / a persisted value, like the serial already is).
**Status:** DONE (code, 2026-08-12) — `unified-wifi-mesh.bbappend` now persists the
AL-MAC base in `/nvram/em_al_base_mac` (seeded from wlan0 on first boot); every later
boot reads the persisted value, so the AL-MAC is stable across a normal redeploy
regardless of which phy the pool allocated (closes the proven "new AL-MAC + old
RUIDs" gap), and `bpi.sh -F` wipes `/nvram`, regenerating AL-MAC + RUIDs together.
Identity is now preserved-or-regenerated as a unit via a single source of truth.
**VALIDATED end-to-end (2026-08-12)** on rev150 with a freshly-built image
(bpiap-003 throwaway): first boot seeded `em_al_base_mac`=`02:00:00:00:09:00` from
wlan0 and derived AL-MAC (`eth1_virt_peer`)=`…09:20`; a normal redeploy preserved
both across the nvram volume; and the decisive decoupling check — setting the
persisted base to a distinct `…aa:00` and restarting — made the AL-MAC follow the
**file** (`…aa:20`) while wlan0 stayed `…09:00`, proving the AL-MAC is derived from
persisted `/nvram`, not the phy. `bpi.sh` `-F` help text updated to match the new
reality. Recipe compile-validated (cleansstate do_patch+do_compile pass).

### 2. Layer unconditionally disables 6 GHz for HWSIM_RADIO — blocks the proven 7.0 6 GHz
`ccsp-one-wifi 0006-wifi_db-disable-6ghz-only-under-hwsim.patch` sets
`cfg.enable=false` for the 6 GHz band on **every** `HWSIM_RADIO` build. But this
repo's own `6ghz.md` (appendix) proves stock 7.0 hwsim beacons
+ associates on 5975 (SAE-H2E, PMF, 4-way handshake). So today EasyMesh can never
exercise 6 GHz even where the kernel supports it.
**Fix direction:** don't `HWSIM_RADIO == no 6 GHz`. Gate on a capability/config
choice — e.g. `HWSIM_RADIO + HWSIM_6GHZ_CAPABLE → enable wifi2`, else disable — or
runtime 6 GHz-usability detection if OneWifi init makes it practical. Keep the
2-band fallback for the legacy 6.8 environment.
**Status:** DONE (code, 2026-08-12) — patch 0006's disable is now
`#if defined(HWSIM_RADIO) && !defined(HWSIM_6GHZ_CAPABLE)`, and
`ccsp-one-wifi.bbappend` adds `HWSIM_6GHZ_CAPABLE ??= "0"` → `-DHWSIM_6GHZ_CAPABLE`
when set to "1". Default off = byte-for-byte the old behaviour; a 7.0-capable host
builds with `HWSIM_6GHZ_CAPABLE = "1"` to keep wifi2 enabled. **Done (2026-08-14):**
a `HWSIM_6GHZ_CAPABLE=1` build brings up tri-band (2.4 + 5 + 6 GHz) concurrently on
the 7.0 rev120 target — see [6ghz.md](6ghz.md).

### 3. Security overrides are incompatible with standards-correct 6 GHz
The EasyMesh bbappend rewrites the seeded controller policy globally
(`WPA3 Personal → WPA2 Personal`, MFP `Required → Optional`), and OneWifi forces
HWSIM AP/STA defaults away from WPA3/SAE. 6 GHz **mandates** SAE-H2E + PMF, so if
we merely enable `wifi2` the controller's M2 would carry a policy that can't make
a standards-correct 6 GHz VAP.
**Fix direction:** make the security config **band/capability-aware** — the
global `HWSIM_RADIO → WPA2` assumption must not apply where `wifi2` participates.
Also: the 6 GHz SAE-H2E flow is PROVEN only with **external** hostap/wpa 2.13 +
kernel 7.0; the **embedded RDK libhostap 2.11** 6 GHz SAE-H2E path is UNPROVEN.
**Fix direction:** add an explicit **6 GHz acceptance gate** proving embedded
2.11 does the same 5975 SAE-H2E association.
**Status:** DONE (code, 2026-08-12) — patches 0005/0007 now force WPA2 only under
`HWSIM_RADIO && !HWSIM_6GHZ_CAPABLE`, so a `HWSIM_6GHZ_CAPABLE=1` build restores the
WPA3/SAE/MFP-required defaults (capability-aware, per the reviewer's "band-aware OR
capability-aware"). Default off is unchanged. **Done (2026-08-14):** the finer
band-scoped split (WPA2 backhaul + 2.4/5 GHz, WPA3/SAE on 6 GHz only) is implemented
via the M2 auth-upgrade guard (Fix B) + coherent cipher/PMF (Fix C), and the
**embedded-stack 6 GHz SAE-H2E + PMF acceptance gate PASSED** — a client associates
to the deployed extender's `wifi2` at 6135 MHz with `key_mgmt=SAE`, `pmf=2`, `BIP`
(the deployed RDK stack, not external 2.13). See [6ghz.md](6ghz.md).

### 4. Gate B still incomplete — disabled radios are only *skipped*, not *excluded*
`unified-wifi-mesh 0003-topo-query-do-not-wait-for-disabled-radios.patch` is
correct for what it fixes (excludes a disabled radio from Topology-Response
readiness / operational-BSS reporting / `topo_synchronized`), but a disabled
radio still gets an `em_t` stuck permanently in `em_state_agent_unconfigured` —
the patch treats the symptom downstream. The general invariant is missing:
`radio_info.enabled == false` → **do not** create it as an onboarding participant,
**do not** fan out `dev_init` to it, **do not** generate M1 for it.
**Fix direction:** exclude disabled radios at dev-init/onboarding/M1 generation,
not just at Topology-Response time. Matters beyond 6 GHz (any admin-disabled radio
could reproduce the class of problem).
**Status:** DONE (code, 2026-08-12) — new patch **0019** skips `create_node()` in
`em_orch_agent`'s `dm_orch_type_em_insert` loop when `radio_info.enabled == false`,
so a disabled radio is retained in the data model but gets no state machine (no
dev_init/M1). Authored against the real source (PR #755) and `git apply --check`
clean. **Residual (documented, not fixed):** controller-side
`em_capability.cpp:handle_ap_radio_basic_cap()` still sets `radio_info->enabled =
true` unconditionally (the AP Basic Capability TLV carries no enabled bit); with
0019 the agent no longer reports a disabled radio, so the controller doesn't learn
it — but the unconditional set is still latent if a disabled radio is ever reported.

## P2

### 5. hwsim 6 GHz build tooling is pinned to the obsolete 6.8 model
`gen/hwsim/build-hwsim.sh` is pinned to `6.8.0-136-generic` / `linux-hwe-6.8`
(refuses another kernel without `FORCE=1`), and its `--6ghz` mode applies
`0002` which assumes `regtest=5 → custom_01` and adds `REGULATORY_STRICT_REG`.
The 7.0 result proves stock 7.0 already has `regtest=5 → custom_03` and 6 GHz
IR-capable. The tooling should **distinguish kernel generations** rather than
encourage `FORCE=1` against 7.0; for 7.0 the useful config is closer to
*stock/current hwsim + multichannel relaxation (if needed) + channels=3 +
regtest=5*, not the old strict-regdom patch.
**Status:** DONE (2026-08-12) — `build-hwsim.sh` is now kernel-generation aware:
parses major.minor from `uname -r`, supports 6.8 **and** 7.0 without `FORCE`,
derives the `linux-hwe-<gen>` apt source package, and branches `--6ghz` (6.8 → the
strict-regd patch 0002; 7.0 → no regd patch, `--load` uses `regtest=5` +
`channels=3`). `bash -n` clean; generation parse verified.

### 6. Docs contradict the repo's own 7.0 6 GHz result
`architecture.md`, `deploy-and-test.md`, `patches.md` still state 6 GHz is NO-IR /
`wifi2` logical-only / "can never beacon", while the repo also contains the 7.0
result proving stock 6 GHz works. Separate the documented platforms:
**Legacy 6.8 lab** (channels=2, 2.4+5, wifi2 disabled, NO_IR) vs **7.0 lab**
(channels=3, custom_03/regtest=5, 2.4+5+6 candidate, 5975 AP/STA proven, EasyMesh
tri-band still to validate). Makes the evidence boundary clear.
**Status:** DONE (2026-08-12) — `architecture.md`, `deploy-and-test.md`,
`patches.md` (rows 0005/0006 + hwsim category), `wmediumd-multichan.md`, and the
README index now split legacy-6.8 vs 7.0 and cross-link the 7.0 results.

### 7. Single-association fix (0017) is not MLO-safe
`0017-dm-enforce-single-association-invariant.patch` deletes every other-BSS
attribution for the same STA MAC before storing the new association — correct for
non-MLO (AP-A→AP-B), but wrong for a genuine MLO station with legitimate
simultaneous link-A + link-B associations. Its own comment scopes it to
"non-MLO station records". No MLO guard exists.
**Fix direction:** distinguish MLD/link associations before making
single-association the permanent data-model invariant (matters as Wi-Fi 7 / 6 GHz
become realistic here). Not a current blocker.
**Status:** DONE (code, 2026-08-12) — 0017's `enforce_single_assoc()` now returns
early under `#if defined(EM_MLO_SUPPORT)` (undefined by default, so today's non-MLO
behaviour is byte-for-byte unchanged). An MLO build defines the macro, which
compiles the blanket enforcement out and MUST replace it with per-MLD/per-link
handling (compare MLD MAC + link, not just STA id + BSSID). `git apply --check`
clean. Full runtime per-link logic still needs the MLD struct field (not authorable
blind in this nosrc layer).

## P3

### 8. Steering ACK fallback can still hit an arbitrary radio
`0011-steering-route-1905-ACK-to-the-requesting-radio.patch` correctly correlates
`source AL-MAC + MID + pending steering state`, but on no-match falls back to the
**first non-AL radio in `m_em_map`** (old arbitrary behaviour); `0013` has a
similar agent-side BTM-report-ACK fallback.
**Fix direction:** on no match, **log/ignore** (or route to a generic non-steering
ACK handler) rather than "first radio". Hardening, not a proven current defect.
**Status:** DONE (code, 2026-08-12) — both 0011 (`em_ctrl.cpp`) and 0013
(`em_agent.cpp`) drop the "first non-AL radio in `m_em_map`" fallback and leave
`em == NULL` on no match, so the caller drops the unmatched ACK (the caller already
handles NULL for unmatched messages). Same line count → hunk headers unchanged. A
logging line was left out only because `em_printfout`'s presence in those TUs can't
be confirmed in this nosrc tree; the drop-comment documents the behaviour.

## Known-good (per the review — do not regress)
- Steering series: `0010` validates source-BSSID-local + STA-actually-associated
  before the BTM request and derives the VAP dynamically (no hardcoded 2412/ap0).
- Disabled-radio Topology-Response patch has a clean ownership boundary.
- `bpi.sh` correctly encodes the one-phy-per-FEATURE_SINGLE_PHY invariant.

## Related open item (from the parallel policy probe)
No **active** steering policy is in place — `PolicyList` empty, per-radio
`SteeringPolicy`/RCPI/util thresholds all `0`, no Multi-AP Policy Config pushed to
agents. Autonomous/policy steering also needs an RSSI gradient (wmediumd);
commanded steering (`steer.sh`) works regardless. Track under a future
"enable + verify a steering policy" task.
