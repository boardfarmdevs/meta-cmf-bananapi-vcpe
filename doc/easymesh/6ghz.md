# 6 GHz EasyMesh on Linux 7.0 (hwsim)

Building the Banana Pi RDK-B images and running them in `HWSIM_6GHZ_CAPABLE`
(6 GHz) mode over `mac80211_hwsim` on a Linux 7.0 kernel. This is the single record
of the 6 GHz work: the kernel setup (6.8 vs 7.0), the issues found and fixed, the
end-to-end EasyMesh bring-up, and — appended at the end — the standalone hwsim
6 GHz VLP-AP verification that proved the kernel/hwsim side independently.

## Setup — hosts and kernels (6.8 vs 7.0)

| Host | Kernel | Role |
|---|---|---|
| `rev140` | 5.15 (Ubuntu 20.04) | **build host** — builds the two LXC images (userspace only, not a run kernel); git source-of-truth for this layer |
| `rev150` | **6.8**.0-136 | earlier run host — 2.4 + 5 GHz mesh works; predates the 6 GHz work |
| `rev120` | **7.0**.0-28-generic (Ubuntu 24.04) | **the 6 GHz run target** — runs the LXD/hwsim lab |

**Why 7.0 is the run target.** The 6 GHz work needs the kernel's modern 6 GHz
regulatory/AP path (VLP-AP flags, `he_6ghz_reg_pwr_type`) that 7.0 has and the 6.8
run host does not. On 7.0, `mac80211_hwsim` loaded with `regtest=5` selects the
`custom_03` domain, which leaves 6 GHz **IR-capable** — so an hwsim 6 GHz AP can
beacon with no kernel change at all (proven standalone at 5975 MHz; see the
appendix). Under 6.8 the applied domain left 6 GHz NO_IR, which is why the earlier
lab never saw 6 GHz.

**What 7.0 cost — a single-phy regression (Issue F1).** The same 6.8→7.0 jump that
opens 6 GHz also made 7.0 reject a standalone `SET_WIPHY`+`WIPHY_FREQ` channel-set
once a sibling AP on the one hwsim phy is already beaconing — which 6.8 tolerated.
That (not a kernel *limit*) is why at first only wifi0 came up; it is fixed in the
HAL by carrying each radio's channel through `START_AP` (patch 0022). The kernel
comparison that isolated it: rev150 **6.8** brought wifi0 + wifi1 up on one phy,
while rev120 **7.0** brought only wifi0 up with a persistent `-22` on the 2nd/3rd
radio until 0022.

Everything below runs on the **7.0 / rev120** target with images built on rev140.
The capability flag itself is [TODO.md](TODO.md) #2/#3.

## Verdict

**Build: SUCCESS. 6 GHz build + config: PROVEN. Issue F split: F1 (2nd/3rd-radio
bring-up regression) root-caused and FIXED — 2.4 + 5 GHz now concurrent. F2 (6 GHz AP
regulatory blocker) — **ROOT-CAUSED and FIXED; acceptance PASSED**: the observed wifi2 `-EINVAL` is
a *regulatory-provisioning* defect — OneWifi's HAL defaults the country to `US` (platform
default-country hook absent → hardcoded US fallback), whose 6 GHz is PASSIVE/no-IR in
wireless-regdb, so wifi2's START_AP meets a no-IR channel and fails `-EINVAL`. First
proven the blocker by an A/B/C/D standalone-hostapd matrix under a held IR reg (6135
AP-ENABLED alone AND as a 3rd concurrent AP on one phy); then **confirmed on the real
OneWifi path**: fix 0008 (`HWSIM_RADIO`-gated) defaults the hwsim build to a 6 GHz-IR
domain (GB), and after rebuild+redeploy the real OneWifi brings up **tri-band (2.4 + 5 + 6
GHz) concurrent AP-UP on one hwsim phy on kernel 7.0** (core reg GB, 6135 `23 dBm` IR,
wifi0/1/2 all up, stable). NOT an hwsim concurrency, channel-37, op-class, or width
problem — only the default country. Real BananaPi R4 keeps its platform/US default
(hwsim-only).**

Two committed patches (0022 + 0008) took the runtime from *only wifi0 beaconing* to all
of **wifi0 + wifi1 + wifi2 (2.4 + 5 + 6 GHz) AP-UP concurrently on the single hwsim phy
on kernel 7.0**. 0008 carries three logically independent `HWSIM_RADIO` changes:

- **rdk-wifi-hal 0022** — under `FEATURE_SINGLE_PHY`, skip the standalone
  `SET_WIPHY`+`WIPHY_FREQ` channel-set in `nl80211_update_wiphy()`; let `START_AP`
  carry each VIF's channel. (F1a: 7.0 rejects that standalone set once a sibling AP is
  active. Result: wifi0 up, `setRadioOperatingParameters` `-22` gone.)
- **ccsp-one-wifi 0008a** — under `HWSIM_RADIO`, clamp `channelWidth` to 20 MHz (F1b —
  **proven for 5 GHz**: wifi1 @80 MHz → START_AP failure, @20 MHz → AP-UP. For 6 GHz the
  width is **not** an established cause: wifi2 failed at both 160 and 20 MHz with NO_IR
  present. Result: wifi1 (5 GHz) up).
- **ccsp-one-wifi 0008b** — under `HWSIM_RADIO`, set the 6 GHz operating class to 131 so
  it agrees with the 20 MHz width (op-class encodes width; refuted as *the* 6 GHz cause
  but keeps the config self-consistent).
- **ccsp-one-wifi 0008c** — under `HWSIM_RADIO`, default the country to **GB** (a 6 GHz-IR
  domain). This is the **F2 fix**: the HAL's platform default-country hook is absent so
  the country otherwise falls back to US, whose 6 GHz is PASSIVE/no-IR, blocking wifi2's
  START_AP. With GB, the real OneWifi brings wifi2 (6 GHz) up. Result: **wifi2 (6 GHz) up**.

Historical F2 failure before 0008c: **wifi2 (6 GHz, ch37/6135) failed `-22`** even at
20 MHz.
Ruled out: context-count (three concurrent 20 MHz APs — 2437+5180+5240 — all AP-ENABLED
on one phy), generic 6 GHz capability (standalone 6 GHz proven at 5975 under an
IR-capable reg), and the width/op-class mismatch (0008 now sets op class 131 + 20 MHz,
verified — still `-22`). **ROOT-CAUSED and FIXED: regulatory NO_IR.** In this run 6135
reads `12 dBm (no IR)` because the HAL defaults the country to `US` (its platform
default-country hook is absent → hardcoded US fallback), and US 6 GHz is PASSIVE/no-IR;
on a no-IR channel `cfg80211_reg_check_beaconing()` fails → the exact `-EINVAL` wifi2
hits. This is why the standalone 5975 case (no OneWifi, core stayed custom_world) works
and the US-provisioned RDK 6 GHz did not. An A/B/C/D standalone-hostapd matrix under a
held IR reg first isolated it (6135 AP-ENABLED alone AND as a 3rd concurrent AP on one
phy). **Acceptance PASSED:** after extending 0008 so `HWSIM_RADIO` defaults the country
to GB, the rebuilt/redeployed controller brought up the **real OneWifi** wifi2 at 6135,
with wifi0 + wifi1 + wifi2 concurrently AP-UP on one phy (core reg GB, 6135 `23 dBm` IR).
The only variable changed was the default country — same OneWifi state machine, same HAL
channel path — proving the chain end-to-end (see Issue F2).

- The images build from scratch on rev120, but **only inside an Ubuntu 20.04
  container** — a native 24.04 build fails (pseudo/gcc-13/python; see below).
- `HWSIM_6GHZ_CAPABLE=1` works **at the local OneWifi/HAL config layer**: the 6 GHz
  radio (`wifi2`) and its VAPs are created (they are *absent/disabled* without the
  flag), and OneWifi builds a **standards-correct 6 GHz hostap config** (band 3, op
  class 131 post-0008 / was 134, ch 37 / 6135 MHz, **SAE-H2E** `sae_pwe=1`). This
  confirms review #2 and proves the **local OneWifi/HAL 6 GHz-security configuration
  portion** of #3.
- The pre-fix runtime beaconed **only wifi0 (2.4 GHz)**; the full root-cause chain and
  the two fixes above are in *Issue F* and *Fixes applied & acceptance* below. The
  kernel was proven **not** the limit (concurrent multichannel works on 7.0 via the
  AP-start path); **F1** was OneWifi/HAL sequencing + wide-channel defaults (fixed),
  **F2** (6 GHz) is a separate failure class — regulatory NO_IR from the HAL's US default
  country — root-caused, **fixed (0008 → GB) and accepted on the real OneWifi path**.
- The **controller → WSC M2 → extender** 6 GHz-security path and the **B+C encoding fixes**
  were first demonstrated on a timing-lucky hot-swap run, then the backhaul 4-addr /
  WDS-before-authorization race that blocked the **clean rev140 deployment** was root-caused and
  **fixed** (defer WDS-STA setup until authorization — rdk-wifi-libhostap 0003/0004 — and create it
  from the HAL `SET_STATION(authorized)` path — rdk-wifi-hal 0023). **On the clean rev140 deploy the
  whole chain now runs end to end:** backhaul 4-way completes (0 reason-15), the WDS bridges into
  `brlan0`, the extender onboards (DeviceList 1→2, BSSList 10→20), per-radio WSC M2 is applied, and the
  **6 GHz fronthaul AP (`wifi2`, `private_ssid`, ch 227 / 6135 MHz) is up on both nodes**. The **#3
  security acceptance PASSES**: `wifi2` beacons `SAE` + `MFP-required`, and a SAE-H2E client associates
  (`key_mgmt=SAE`, `pmf=2`, `mgmt_group_cipher=BIP`, `wpa_state=COMPLETED`). See the #3 section below.

## Build — native 24.04 fails; 20.04 container succeeds

A from-scratch build on the 24.04 host hit the classic "old OE on too-new host"
cascade; each was root-caused:

| Failure | Cause | Fix |
|---|---|---|
| HOSTTOOLS `python` missing | 24.04 ships only `python3` | `apt install python-is-python3` |
| breakpad-native `uintptr_t does not name a type` | gcc-13 dropped transitive `<cstdint>` | inject `<stdint.h>` (bbappend; C+C++ safe) |
| **`do_package` fails for every recipe** | **pseudo/fakeroot broken on 24.04 glibc** (`got *at() syscall for unknown directory`) | **build in a container** |
| ieee1905-em (Rust) `bits/libc-header-start.h not found` | 32-bit-target bindgen needs multilib headers | `gcc-multilib` + `libc6-dev-i386` in the image |

**Solution:** build in an **Ubuntu 20.04** Docker container (= rev140's proven
userspace), bind-mounting the tree + the 64 GB downloads at their real paths, run as
uid 1000 with `--security-opt seccomp=unconfined`. pseudo/`do_package` then work.
Both images build clean (broadband 5792 tasks, ap 4988 tasks, exit 0). The kernel
stays 7.0 for the LXD/hwsim runtime (the container is build-only). See memory
`rev120-6g-build-setup`.

## 6 GHz enablement — PROVEN at build + config

- Rebuilt with `HWSIM_6GHZ_CAPABLE = "1"` (local.conf). Deployed controller image
  `X86EMLTRBPIBB_..._20260813115758`.
- Host hwsim pool `radios=24 channels=3 regtest=5` = `HWSIM_REGTEST_CUSTOM_WORLD`:
  applies an IR-capable custom-world 6 GHz rule (`5945-7135 @ 33 dBm`, no passive flag)
  to every radio via **non-strict** `REGULATORY_CUSTOM_REG`. **Right after `modprobe`,
  6 GHz is IR-capable (0 no-IR).** But because it is non-strict, a later core-reg change
  to `country US` (whose old-regdb 6 GHz rule is `5925-7125 @ 12 dBm, NO-OUTDOOR,
  PASSIVE-SCAN` = **no-IR**) **intersects it down and flips every 6 GHz channel to
  no-IR**. See the Issue-F2 regulatory finding below — 6 GHz IR-capability is a *mutable*
  state here, not a fixed property, and must be verified at the moment of START_AP.
- The container has **`wifi2`, `wifi2.1`, `wifi2.2`** (6 GHz radio + VAPs) — these do
  **not** exist without the flag. OneWifi's HAL configures `wifi2.1`:

  ```
  # post-0008 (channelWidth clamp + 6 GHz op-class 131); pre-0008 this was op class:134
  update_hostap_iface: interface name:wifi2.1 country:US op class:131
                       global op class:131 channel:37 frequency:6135
  update_security_config: interface_name:wifi2.1 sae_pwe:1          # SAE-H2E
  update_hostap_bss: Enabled multi_ap:1 for interface:wifi2.1       # EasyMesh backhaul
  ```

  i.e. a 6 GHz VAP with mandatory SAE-H2E — exactly what review #3 (restore SAE/WPA3
  under the capability flag) is for. Without it, `wifi2` would be WPA2 and disabled.

### #3 evidence boundary — encode + backhaul both ROOT-CAUSED + FIXED + VALIDATED on the clean rev140 deploy; 6 GHz SAE-H2E + PMF acceptance PASSED

```
Controller/agent security-provisioning defect        ROOT-CAUSED
Fix B: 6-GHz WPA2PSK -> WPA3/SAE upgrade (guard)      IMPLEMENTED (unified-wifi-mesh 0011)
Fix C: mode/cipher + PMF coherence (AP + STA)         IMPLEMENTED (ccsp-one-wifi-libwebconfig 0002)

private-subdoc encode                                PASSES 3/3 (hot-swap + clean rev140 deploy; was 0/3)
OneWifi config application                           PROVEN (fronthaul AP-UP; "radio not configured" cleared)
setRadioOperatingParameters                          PROVEN (all 3 radios, incl 6 GHz)

clean B+C images built on rev140                     DONE (cffd4f0 reverted -> WPA2 seed/defaults)
both nodes deployed from rev140 images               DONE

backhaul 4-way (4-addr WDS-before-auth)              FIXED + VALIDATED (clean rev140 deploy)
  root cause: WDS netdev created before auth -> M4 diverted -> reason-15
  fix = defer WDS setup until WLAN_STA_AUTHORIZED, then create from the
        HAL SET_STATION(authorized) path
        rdk-wifi-libhostap 0003/0004 (defer) + rdk-wifi-hal 0023 (create-at-auth)
  proof: 0 reason-15, "received eapol m4", wifi1.1.sta1 master=brlan0 oper=up

extender onboarding (1905 search crosses backhaul)   VALIDATED (DeviceList 1->2, BSSList 10->20)
per-radio WSC M2 (private/backhaul/iot)              VALIDATED ("Authenticator verification succeeded")
fronthaul AP bring-up                                VALIDATED (private_ssid AP up on wifi0/1/2)
wifi2 6 GHz fronthaul AP                              UP (type AP, ch 227 / 6135 MHz, 23 dBm, both nodes)

#3 ACCEPTANCE — 6 GHz SAE-H2E + PMF                  PASSED (clean rev140 deploy)
  extender wifi2 beacon (6135)                       SAE AKM + MFP-required (scan RSN)
  client SAE-H2E assoc to wifi2 (5d:4a:88)           PASSED (wpa_state=COMPLETED)
  key_mgmt / PMF / mgmt cipher                        SAE / pmf=2 / BIP
  AP-side station authorized+authenticated           PROVEN (iw station dump, wifi2)

ONEWIFI-RESTART CONFIG REPLAY                        ROOT-CAUSED + FIXED + VALIDATED
  cause: OneWifi config in-memory; no WebConfig-framework daemon to answer its
         post-crash re-push signal; em_agent never observes the restart
  fix:   em_agent.service PartOf=onewifi.service (unified-wifi-mesh.bbappend, ext only)
  proof: restart onewifi -> fronthaul (incl 6 GHz) auto-recovers ~36s, no manual em_agent

ACTIVE
  wifi0.1/wifi1.1 empty backhaul-AP slots            OPEN  <-- layout check
  downstream wifi2.1 client                          NOT TESTED
  data throughput after SAE association              NOT TESTED
```
(**The encode root cause is fixed in the running system** (mismatched **WPA2-Personal + AES-GCMP-256**
tuple `encode_security_object` rejected; Fix B upgrades the 6 GHz M2 to WPA3/SAE, Fix C sets a
coherent `AES/CCMP` cipher + PMF-for-WPA3 in AP **and** STA branches). **The clean rev140-image deploy
then exposed — and the WDS-defer fix then resolved — the controller-side backhaul defect**: a 4-addr
trade-off on `mac80211_hwsim` where the HAL created the WDS netdev on the **first 4-addr frame (M2),
before authorization**, diverting M4 → reason-15, while disabling the extender's `sta_4addr` completed
the 4-way but un-bridged the backhaul so the 1905 search could not cross. The fix keeps the extender
in 4-addr mode but **defers WDS-STA creation until `WLAN_STA_AUTHORIZED`** (rdk-wifi-libhostap
0003/0004) and **creates it from the HAL `SET_STATION(authorized)` path** (rdk-wifi-hal 0023, the
reliable trigger — a leftover WDS netdev otherwise suppresses `UNEXPECTED_4ADDR`). **Both sides of the
trade-off now hold on the clean rev140 deploy:** the 4-way completes (M4 received, 0 reason-15) **and**
the bridged 4-address path is established (`wifi1.1.sta1 master=brlan0`), so onboarding completes and
the whole chain runs through to the **6 GHz fronthaul AP up on both nodes**. See the top *#3 evidence
boundary* / *Completed — 6 GHz SAE-H2E / PMF acceptance* block.)

## Issue F — F1 CLOSED; F2 CLOSED

The original symptom (only wifi0 configures; wifi1 + wifi2 never START_AP) exposed a
**layered failure**. F1 contained two bring-up barriers: **F1a** the standalone
pre-START_AP channel-set (→ 0022), and, independently for 5 GHz, **F1b** the 80 MHz
default (→ 0008a). Once those were removed (wifi0 + wifi1 AP-UP), **F2** emerged as a
distinct *later* 6 GHz START_AP failure — a regulatory one, fixed by 0008c. They must not
be conflated.

```
F1a  standalone channel-set sequencing   -> 0022  -> CLOSED
F1b  5-GHz 80-MHz default                 -> 0008a -> CLOSED
     => wifi0 + wifi1 AP-UP
F2   HWSIM default country US
       -> 6-GHz NO_IR
       -> START_AP -EINVAL
       -> 0008c HWSIM default country GB
       -> real OneWifi tri-band AP-UP    -> CLOSED
```

> **Issue F1 — second-radio bring-up regression — CLOSED.**
> Barrier 1: a standalone pre-START_AP `SET_WIPHY`+`WIPHY_FREQ` channel-set that 7.0
> rejects `-EINVAL` once a sibling AP on the phy is active → fixed by **0022** (let
> START_AP carry the channel). Barrier 2 — proven for **5 GHz only**: wifi1 @80 MHz →
> START_AP failure, @20 MHz → AP-UP → fixed by **0008** (clamp to 20 MHz). (6 GHz is
> *not* covered by this barrier: wifi2 fails at both 160 and 20 MHz with NO_IR present,
> so width causality is not established for 6 GHz — that is F2.) **Result: wifi0 (2.4) +
> wifi1 (5) are concurrently AP-UP on one hwsim phy on kernel 7.0.** Proven.

> **Issue F2 — 6 GHz AP regulatory blocker — ROOT-CAUSED, FIXED, ACCEPTED — CLOSED.**
> wifi2 @ 6135 failed `-EINVAL` at the START_AP channel set because the HAL defaults the
> country to `US` (platform default-country hook absent → hardcoded US fallback), and US
> 6 GHz is PASSIVE/no-IR in wireless-regdb — so wifi2 met a no-IR channel and
> `cfg80211_reg_check_beaconing()` → `-EINVAL`. An A/B/C/D standalone-hostapd matrix under
> a held IR reg (GB) first isolated it (6135 AP-ENABLED alone **and** as a 3rd concurrent
> AP on one phy). **Ruled out** (for the observed 20 MHz failure): hwsim concurrency,
> context-count, channel-37/6135 specifics, op-class (131), and width. **Not tested / not
> required:** concurrent 160 MHz 6 GHz capability. **Fix (0008c, `HWSIM_RADIO`):** default
> the country to a 6 GHz-IR domain (GB) — no wireless-kernel *capability* or HAL
> channel-path change. **Accepted:** after rebuild+redeploy the **real OneWifi** brings up
> tri-band (2.4 + 5 + 6 GHz) concurrent AP-UP on one phy (core reg GB, 6135 `23 dBm` IR,
> wifi0/1/2 all up). Only the default country changed — same state machine, same channel
> path — so the causal chain is proven end-to-end on the identical OneWifi request.

### F2 regulatory finding — 6 GHz is no-IR under the US default (the root cause, now fixed)

The single-phy dual-band diagnosis below correctly found 5 GHz was **not** reg-blocked
(ch36/40/48 at `23.0 dBm`). That does **not** extend to 6 GHz, and 6 GHz IR-capability
here is **mutable**:

- `regtest=5` (CUSTOM_WORLD) is **non-strict**, so custom-world's IR-capable 6 GHz rule
  is authoritative only until the core reg changes. Right after `modprobe`, 6 GHz shows
  **0 no-IR** (the earlier capture in this doc). **In the failing pre-0008c run**, the
  effective core reg is `country US: DFS-FCC`, whose old-regdb 6 GHz rule is
  `5925-7125 @ 12 dBm, NO-OUTDOOR, PASSIVE-SCAN` = **no-IR**, which intersects the
  custom-world rule down: **every** 6 GHz channel on **both** the container phy119 and
  free host pool phys now reads `12 dBm (no IR)` — 5975 included.
- Reversible core-reg probe (host, restored after): core=US → 6135 `no IR`;
  core=00 → 6135 `disabled`. Two distinct routes restore IR capability: a fresh
  `modprobe … regtest=5` restores the *original* custom-world `33 dBm` IR state (the
  one the standalone proof used), **or** `iw reg set GB` produces a *distinct but
  usable* `23 dBm` IR-capable state **without** reloading hwsim. So only the original
  custom_world state needs the reload — IR capability itself does not.
- `cfg80211_reg_check_beaconing()` failing on a no-IR channel returns exactly the `-EINVAL`
  wifi2 hit at the START_AP channel set. In the failing pre-0008c run, regulatory was the
  **first-order** blocker, and it invalidated a 5975-alone control until the reg was pinned
  IR-capable.

**Matrix prerequisite used:** each case was run under an observed IR-capable GB
regulatory state, verified at START_AP time (case A / 5975-alone establishes the control
under that reg). See the completed matrix results below.

#### Historical pre-0008c proof: OneWifi re-imposed the US/no-IR state (deterministic, reproducible)

A pure core-reg toggle **is** achievable without a `modprobe`: this host's regdb has
IR-capable 6 GHz LPI rules under GB/DE/JP/AU (`iw reg set GB` → 6135 = `23 dBm`, **no**
NO_IR) — the intersection with the phys' custom-world clears NO_IR. Set on the host, it
propagates into the container's netns (phy119). Using that as the toggle:

```
core=US  ->  phy119 6135 = 12 dBm (no IR)   [state X]
iw reg set GB (pure core-reg change, nothing else)
core=GB  ->  phy119 6135 = 23 dBm, IR-ok    [state Y]   ✓ NO_IR tracks the core domain
```

**Before 0008c, the RDK path re-created state X on its own.** Restarting `onewifi.service` while
core=GB flips the core reg back to `country US` within ~8 s — reproducibly — and 6135
returns to `12 dBm (no IR)`:

```
before onewifi restart:  core=GB   6135 = 23 dBm, IR-capable
~8 s after restart:      core=US   6135 = 12 dBm, (no IR)   wifi2.1 down
```

So the F2 chain is: `OneWifi startup → country US (11d/reg hint) → core reg US →
old-regdb US 6 GHz = PASSIVE/no-IR → intersect custom-world → 6135 no-IR →
`cfg80211_reg_check_beaconing()` fails → START_AP `-EINVAL``. This is why the standalone
5975 proof (no OneWifi, core stayed custom_world) worked and the pre-0008c RDK 6 GHz path
did not: **before 0008c, OneWifi guaranteed a no-IR 6 GHz state at the moment it tried to
bring wifi2 up.**

#### PROVEN: the A/B/C/D matrix closes the last boundary

The final boundary — *does an **equivalent** 6 GHz AP succeed once NO_IR is removed?* —
was proven with a **standalone hostapd matrix on a spare host phy under a held `iw reg
set GB`** (OneWifi obstructs its own retry: it re-hints US at startup, and once it marks
Radio.3/AP.17 `Status=Up` while the netdev is `down` it does **not** retry START_AP, so
dmcli toggles are no-ops — hence standalone hostapd with a *matched* config, not the
identical OneWifi netlink request: op_class 131, HE, 20 MHz, SAE-H2E/PMF). Each case
verified an IR-capable 6135 at START_AP time:

```
A  5975 alone            -> AP-ENABLED, operstate up, ch5/5975 20 MHz   (control PASSES)
B  6135 alone            -> AP-ENABLED, operstate up, ch37/6135 20 MHz
C  5975 3rd concurrent   -> 2437 + 5180 + 5975 all AP-UP on ONE phy
D  6135 3rd concurrent   -> 2437 + 5180 + 6135 all AP-UP on ONE phy (ch37/6135 20 MHz)
```

All four pass. So an equivalent 6 GHz AP reaches AP-ENABLED **both alone and as a 3rd
concurrent context on a single phy** once the reg is IR-capable — even without any
`he_6ghz_reg_pwr_type` (hostapd's own `country_code=GB`+`ieee80211d` re-hints GB and it
beacons). **This isolated regulatory NO_IR as the cause of the observed wifi2 `-EINVAL` at
20 MHz — NOT an hwsim 6 GHz concurrency problem, not channel-37/6135-specific, not
op-class, and NOT a width problem** (concurrent 160 MHz 6 GHz capability is neither
established by the matrix nor required to explain the observed 20 MHz failure). The RDK
wifi2 met a no-IR channel because the HAL defaults the country to `US` (US 6 GHz =
PASSIVE/no-IR) at radio bring-up. The one boundary not exercised by the matrix — the
*identical* OneWifi wifi2 START_AP under an IR reg — was then closed by the acceptance run
below (0008c default country → GB → real OneWifi tri-band AP-UP), proving the chain
end-to-end with no second downstream defect.

**F2 fix (regulatory provisioning/configuration):** stop the effective 6 GHz reg being
no-IR at START_AP — e.g. keep the core reg in a 6 GHz-IR domain (don't let OneWifi force
US in the hwsim lab), ship a modern `wireless-regdb` whose US 6 GHz carries an LPI-AP IR
rule (and have OneWifi's hostap set the matching power type), or make the hwsim wiphy
`REGULATORY_WIPHY_SELF_MANAGED` so non-local US hints don't override custom-world. **No
wireless-kernel capability or HAL channel-path change is required** (the `SELF_MANAGED`
option is a hwsim-side regulatory-behavior toggle, not a channel-path change). This
hwsim-lab failure should not be generalized to real BananaPi R4 6 GHz hardware with a
correctly provisioned regulatory domain without separate validation.

#### Acceptance run — attempt 1 (runtime routes blocked; superseded by attempt 2)

Tried to make the *real* OneWifi wifi2 START_AP happen under an IR-capable 6135. Every
non-invasive route is blocked:

- **dmcli `Radio.{i}.RegulatoryDomain = GBI`** — accepted then silently **reverts to
  `USI`** (derived param; not authoritative).
- **`WiFiRegion.Code = GBI`** (the authoritative syndication param), set at runtime *and*
  persisted in `/nvram/partners_defaults.json` + OneWifi restart — `Radio.*.RegulatoryDomain`
  reads `GBI`, but the **effective core reg stays `country US`** and 6135 stays no-IR;
  wifi2 stays down. So `WiFiRegion.Code=GBI` does **not** result in an effective
  `country GB` cfg80211 regulatory state in this path (a transient GB hint may or may not
  be emitted — not captured); the HAL subsequently applies its default-country result,
  which falls back to US.
- **Immediate source of the US assertion:** the HAL logs `"unable to get default country
  code setting a US"` — `wifi_hal_get_default_country_code()` returns error (its platform
  hook is absent), so the caller `init_radio_config_default()` (ccsp-one-wifi
  `source/db/wifi_db.c`) leaves the default `wifi_countrycode_US`, which OneWifi applies
  at radio bring-up, overriding `WiFiRegion`. (`/etc/default/crda REGDOMAIN` is empty.)
  *Why* the platform hook is absent is a deeper config question, not needed to prove F2.
- **Runtime forced re-provision** (host reg held `GB`, 6135 verified `23 dBm` IR, then
  `Radio.3.Enable` toggle): reg stayed GB and 6135 stayed IR, but wifi2 **did not** START_AP
  — OneWifi treats `Radio.3`/`AP.17` as already `Status=Up` (netdev `down`) and does not
  retry, so the toggle is a **no-op** (no real START_AP fired → *inconclusive*, not a
  fail-under-IR).

Net (attempt 1): the acceptance is blocked by two OneWifi/HAL behaviors — (1) the HAL
default country `US` overrides the region config, and (2) no runtime START_AP retry for a
radio it thinks is up. Completing it needs the default country itself changed at build
time.

#### Acceptance run — attempt 2 (rebuild) — **PASSED**

Extended **0008** (same `init_radio_config_default()` / `wifi_db.c`) to set
`cfg.countryCode = wifi_countrycode_GB` under `HWSIM_RADIO`, right after the US fallback —
so the hwsim build boots with a 6 GHz-IR domain instead of US. Rebuilt ccsp-one-wifi
(`cleansstate`; do_patch + compile clean) + the broadband image in the 20.04 container,
and **redeployed `bpibroadband` from a free pool phy (no module reload — bng-7/vcpe
untouched)**. Fresh OneWifi bring-up, normal state machine, nothing else changed. Result
(stable 3+ min):

```
core reg = GB: DFS-ETSI     6135 = 23.0 dBm, IR-capable (NO_IR absent)
Radio.3.RegulatoryDomain = GBI
wifi0.1 = up   channel 6  / 2437 MHz  20 MHz
wifi1.1 = up   channel 36 / 5180 MHz  20 MHz
wifi2.1 = up   channel 37 / 6135 MHz  20 MHz   <- 6 GHz AP UP
```

**F2 acceptance PASSED — tri-band (2.4 + 5 + 6 GHz) concurrent AP-UP on one hwsim phy on
kernel 7.0, via the real OneWifi path.** The *only* variable changed was the default
country (US→GB); OneWifi's creation/state-machine and the HAL channel path are untouched,
so this confirms the regulatory root cause end-to-end on the identical OneWifi netlink
request. The observed wifi2 `-EINVAL` was the US-provisioned NO_IR at START_AP, and
nothing downstream — no second defect. **F2 is now FIXED (fix committed in 0008; hwsim-only,
real BananaPi R4 keeps its platform/US default).**

### (original single-phy dual-band diagnosis — the F1 evidence)

Controller booted (no WAN, single hwsim phy = `FEATURE_SINGLE_PHY`). Only **wifi0
(2.4 GHz)** ever configures; **wifi1 (5 GHz)** and **wifi2 (6 GHz)** do not. For the
**5 GHz** radio this is **not regulatory and not a hwsim channel-context limit** (5 GHz
ch36/40/48 are `23.0 dBm`; the phy advertises `#channels <= 3`; `dmesg` shows the
netdevs created with no `EBUSY`/chanctx error). (The 6 GHz reg caveat is the F2 finding
above.)

### The first failing boundary (live wifiHal trace)

Not a hostapd concurrency guess — the HAL log shows the exact boundary. Per radio:

```
setRadioOperatingParameters Index:0 (2.4G ch6  opclass 12)  -> OK          (radio 0 configures)
setRadioOperatingParameters Index:1 (5G  ch36 opclass 128) -> nl80211_update_wiphy dev:23 -22 (EINVAL)
                                                            -> "Failed to update radio : 1"
setRadioOperatingParameters Index:2 (6G  ch37 opclass 134) -> nl80211_update_wiphy dev:23 -22 (EINVAL)
                                                            -> "Failed to update radio : 2"
nl80211_enable_ap (START_AP)  -> -100 (Network is down)   [downstream: iface never configured]
setup_mlo_vap: "MLD interface is enabled, but interface name is unset - skipping"
platform_pre_create_vap: "Failed to setup link for MLD ID 0 with VAP idx N"   [every VAP]
```

Findings, at the boundary the evidence actually supports:

- **`START_AP` *is* attempted** (answering the open question) but returns `-100
  (Network is down)` — a *downstream* symptom.
- The **root boundary is `nl80211_update_wiphy` → `-22 (EINVAL)`** when the HAL sets
  operating parameters for the **2nd and 3rd logical radios** (5 GHz Index:1, 6 GHz
  Index:2) on the single wiphy `dev:23`. **Radio 0 (2.4 GHz) succeeds.** So it is not
  6 GHz-specific — the 2nd radio already fails.
- The HAL sets each logical radio's operating channel; the kernel accepts radio 0 and
  rejects radios 1/2 with `EINVAL`. The on-wire capture below shows these are
  **per-interface** channel-set requests (correct IFINDEX per radio) — see there for
  the precise framing.
- MLD link setup **`skipping` for every VAP** (`MLD interface is enabled, but
  interface name is unset`) — correlated but, per the SET_WIPHY dump below, **not
  causal**.

### The actual on-wire SET_WIPHY (nlmon capture) — MLO/EHT ruled out

Captured the real netlink messages with an `nlmon` monitor in the container netns
(host `tcpdump` via `nsenter`, decoded `tshark -2`), restarting `onewifi` to
re-trigger all three. **Every `NL80211_CMD_SET_WIPHY` frame carries exactly the same
five attributes, differing only in frequency:**

```
                 IFINDEX     WIPHY_FREQ  CHANNEL_WIDTH  CENTER_FREQ1  CENTER_FREQ2   result
radio0 (2.4G)      9 (wifi0)   2437        20 MHz          2437           0           OK
radio1 (5G)        12 (wifi1)  5180        20 MHz          5180           0           -EINVAL
radio2 (6G)        16 (wifi2)  6135        20 MHz          6135           0           -EINVAL
```

Two things are now proven from the message itself:

- No `NL80211_ATTR_MLO_LINK_ID`, no `MLD_ADDR`, no EHT/HE, no TX_POWER, no antenna
  attributes in **any** SET_WIPHY frame (all 9). 10× `-22 (EINVAL)` responses
  correlate with radios 1+2. → MLO/EHT ruled out.
- **The IFINDEX differs per radio: 9 / 12 / 16 = wifi0 / wifi1 / wifi2** (netdev map
  confirmed in the container). So `SET_WIPHY`+`WIPHY_FREQ` here is **not**
  wiphy-global and **not** a "same-netdev" bug: modern cfg80211 uses the supplied
  IFINDEX to route the request into the **per-netdev** channel machinery
  (`__nl80211_set_channel`), and the HAL correctly targets **each logical radio's own
  interface**. Each radio's channel is set on its own wdev.

**So the failure is sharper than "wiphy-global":** on kernel 7.0, with radio 0's
interface (wifi0) up on the shared wiphy, the channel-set request on the **second and
third AP interfaces** (wifi1→5180 IFINDEX 12, wifi2→6135 IFINDEX 16) returns `-EINVAL`
— even though the request is already interface-scoped and hwsim was loaded
`channels≥2`. On 6.8 the same requests succeed. The causal tree:

```
FEATURE_SINGLE_PHY  (one wiphy, three netdevs)
  |
  +-- wifi0 (IFINDEX 9)   set channel 2437  -> PASS
  |
  +-- wifi1 (IFINDEX 12)  set channel 5180  -> -EINVAL   <-- FIRST FAILURE
  |                                              +-> iface stays down
  |                                                    +-> START_AP -> -ENETDOWN  (downstream)
  |
  +-- wifi2 (IFINDEX 16)  set channel 6135  -> -EINVAL   <-- same failure class
```

Two cautions on wording (kept honest to the cfg80211 source): for an AP interface that
has **not** started beaconing (`beacon_interval == 0`), `__nl80211_set_channel()` does
**not** create a mac80211 channel context — it just stores `wdev->u.ap.preset_chandef`
and returns success; the context is established later at `START_AP`. So this is **not**
proven to be "7.0 rejecting a second channel context"; it is **7.0 rejecting the
channel-set request on the 2nd/3rd AP interface, exact cfg80211 state/validation still
open**. And the command is not the lever: **`iw dev … set channel/freq` uses the same
legacy `SET_WIPHY` channel path (CIB_NETDEV), not a separate `SET_CHANNEL`** — so
changing the command name would keep the same `__nl80211_set_channel()` machinery. The
lever is the **AP-start path** (`START_AP` carries the channel), proven below.

**Leading exact-kernel candidate:** upstream commit **`23daf1b4c91d`** *"wifi: nl80211:
disallow setting special AP channel widths"* (2024-05-23) adds two new `-EINVAL` exits
in `__nl80211_set_channel()` that 6.8 lacks — but they run **only when the target
interface's `beacon_interval != 0`**. So it is candidate #1, not yet proven: it only
applies if OneWifi has already started the AP on wifi1/wifi2 before (re)setting the
channel. If `beacon_interval == 0` at the failing call, `23daf1b4` is exonerated and
the `-EINVAL` is elsewhere (`valid_links`/`link_id`, `parse_chandef`, `cfg80211_reg_check_beaconing()`,
or iftype).

### Behavioral regression CONFIRMED (6.8 → 7.0) — exact kernel change still to identify

Ran the discriminators. Both non-kernel dimensions are ruled out; the behavioral
difference is isolated to the kernel, but the exact kernel code path is not yet
pinned:

```
                       kernel        channels   result
rev150   6.8.0-136     ch2           2.4+5 UP, 0 x -22   2nd-radio channel-set WORKS
rev120   7.0.0-28      ch2 AND ch3   only 2.4 UP, -22    2nd-radio channel-set FAILS
```

- **channels-count: RULED OUT** — rev120 fails `-22` at both `channels=2` and `=3`.
- **MLO / EHT / TX-power / antenna: RULED OUT** — absent from the SET_WIPHY message.
- **kernel path: isolated (very strong inference), commit not yet identified** — the
  *only* systemic difference between rev150 (works) and rev120 (fails) is the kernel:
  same HAL, same minimal **per-interface channel-set request**, same `channels`. So the
  relevant behavioral change lives in the 6.8 → 7.0 wireless-kernel path. What this does
  **not** yet prove is that 7.0 *deliberately tightened this specific rule* — that needs
  the responsible cfg80211/mac80211 commit (candidate #1: `23daf1b4c91d`), or booting
  the same rev120 setup under 6.8 and observing it pass. (Irony worth noting: the 7.0
  kernel whose `custom_03` regdomain opens 6 GHz is the one that now rejects the 2nd/3rd
  AP interface's channel-set.)

(An `nlmon` capture of an *onewifi restart* on rev150 showed transient `-22` too, but
that is a restart-on-already-configured-wiphy artifact: 6.8 **recovers** — after it
settles, `wifi0`+`wifi1` are up with 0 `-22`. 7.0 never recovers. The clean signal is
the steady/fresh-boot state, not the restart transient.)

```
PROVEN
------
7.0 rejects the 2nd/3rd AP interface's channel-set (-EINVAL); radio0 succeeds
IFINDEX differs per radio (9/12/16 = wifi0/wifi1/wifi2) -> already interface-scoped,
  routed to per-netdev __nl80211_set_channel(); NOT wiphy-global, NOT same-netdev
6.8 known-good system ultimately accepts equivalent 2-band operation
the channel-set is the first failure; START_AP -ENETDOWN is downstream
attribute sets identical except freq
channels=2 vs channels=3 is NOT causal
MLO / EHT / HE / TX-power / antenna are NOT causal

VERY STRONG INFERENCE
---------------------
the relevant behavioral difference is in the 6.8 -> 7.0 __nl80211_set_channel path
  (candidate: 23daf1b4c91d, gated on target beacon_interval != 0)

OPTIONAL FORENSICS
------------------
the exact cfg80211 validation/commit responsible for the 6.8 -> 7.0 standalone
  channel-set behavioral difference (candidate: 23daf1b4c91d) -- confirmation-only;
  the discriminator below shows it is HAL sequencing, not a kernel limit

CLOSED
------
controller -> extender 6-GHz security
6-GHz SAE-H2E / PMF association
```

### Discriminator — kernel supports it; the failure is HAL sequencing (RESOLVED)

Clean host-hwsim reproduction on rev120 (7.0): one phy, two AP VIFs (`tst0`, `tst1`),
via `iw` + hostapd 2.13, no OneWifi:

```
CONTROL:  iw set tst1 -> ch36, no AP up                 -> rc=0  (success; preset_chandef stored, as cfg80211 documents)
AP up:    hostapd tst0 @ ch6/2437                        -> AP-ENABLED
DISCRIM:  iw set tst1 -> ch36 while tst0 beacons         -> FAIL  (-16 EBUSY)   [standalone channel-set]
TEST2:    hostapd tst1 @ ch36/5180 while tst0 beacons    -> AP-ENABLED          [AP-start path]
```

TEST2 is the answer: **two APs on two different channels come up on ONE phy on 7.0** —
so the kernel is **not** the limit and multichannel is supported. What fails is the
**standalone channel-set** on the 2nd VIF while the 1st AP is active (DISCRIM). Note
that both OneWifi and the `iw dev … set channel` control use the **legacy
`NL80211_CMD_SET_WIPHY` channel-setting path** (upstream `iw` implements `set
channel`/`set freq` via `SET_WIPHY`, CIB_NETDEV form — *not* a separate `SET_CHANNEL`
command). With another AP already active on the phy, that standalone channel operation
fails — `-EINVAL` for the OneWifi request and `-EBUSY` for the iw control (likely
request/state details, not a different nl80211 command). In contrast, carrying the 2nd
VIF's channel in **`NL80211_CMD_START_AP`** succeeds. The observed 6.8 → 7.0 behavioral
difference is **consistent with** 6.8 tolerating OneWifi's standalone-set-while-AP-active
sequence while 7.0 rejects it (the exact same standalone `iw` discriminator has not been
re-run on 6.8; the exact kernel change remains optional forensics). Operationally, **the
AP-start path works on 7.0** and removes the blocker. So **Issue F1 is OneWifi/HAL
sequencing, resolvable on 7.0 today** — no kernel change or downgrade needed. (F2 is a
distinct failure class — regulatory — not this sequencing issue.)

## Fixes applied & acceptance (both stages)

Two patches, built (20.04 container) and deployed on rev120; 0008 carries three
independent `HWSIM_RADIO` changes:

```
0022   F1a: skip standalone SET_WIPHY channel-set (let START_AP carry the channel)
0008a  F1b: HWSIM channelWidth -> 20 MHz
0008b  6 GHz op-class -> 131 (agree with 20 MHz; config consistency)
0008c  F2:  HWSIM default country -> GB (a 6 GHz-IR domain)
```

- **`rdk-wifi-hal` 0022** — `nl80211_update_wiphy()` under `FEATURE_SINGLE_PHY`. Result:
  `setRadioOperatingParameters` `-22` gone, **wifi0 (2.4 GHz) up**.
- **`ccsp-one-wifi` 0008a** — clamp `channelWidth` to 20 MHz in
  `init_radio_config_default()`. Proven for 5 GHz (default 80 → START_AP failure; 20 MHz →
  up). Result: **wifi1 (5 GHz) up**. (For 6 GHz the 160 MHz default also failed, but so did
  20 MHz while NO_IR was present — width causality holds for 5 GHz only.)
- **`ccsp-one-wifi` 0008b** — 6 GHz op-class → 131 (self-consistent with 20 MHz; refuted as
  the 6 GHz cause).
- **`ccsp-one-wifi` 0008c** — default country → GB. Result: **wifi2 (6 GHz) up** (see F2).

**Stage 1 — intermediate (0022 + 0008a/b, before 0008c, country still US):**
```
wifi0.1  up    ch6  (2437 MHz) 20 MHz   BEACONING
wifi1.1  up    ch36 (5180 MHz) 20 MHz   BEACONING
wifi2.1  down  (6135 MHz) -> "Failed to set channel: -22"   (US / NO_IR)
setRadioOperatingParameters -22: 0
```
2.4 + 5 GHz concurrent (the rev150 dual-band baseline on the 7.0 host). Supporting
host-hwsim proof: three concurrent 20 MHz APs (2437 + 5180 + 5240) all AP-ENABLED on one
phy — so the wifi2 failure was **not** a context-count limit. Op-class 131 (0008b) was
tested and refuted (config `op class:131 … 20 MHz` yet wifi2 still `-22`) — pointing at
regulatory (F2), not a chandef/width issue.

**Stage 2 — final (add 0008c, country → GB), fresh real-OneWifi bring-up:**
```
core reg = GB: DFS-ETSI     6135 = 23 dBm, IR-capable
wifi0.1  up  ch6  (2437 MHz) 20 MHz
wifi1.1  up  ch36 (5180 MHz) 20 MHz
wifi2.1  up  ch37 (6135 MHz) 20 MHz   <- F2 fixed
```
**Tri-band (2.4 + 5 + 6 GHz) concurrent AP-UP on one hwsim phy on kernel 7.0 — F2
acceptance PASSED.**

## Next steps

**Completed:**
- **F1a** (standalone pre-START_AP channel-set) — CLOSED (0022).
- **F1b** (5 GHz 80 MHz default) — CLOSED (0008a).
- **F2** (6 GHz regulatory: HAL US default → NO_IR) — CLOSED (0008c), real-OneWifi
  acceptance **PASSED** (tri-band 2.4 + 5 + 6 GHz concurrent AP-UP; re-proven on a fresh
  `-F` controller boot).
- Exact 6.8 → 7.0 kernel change — **OPTIONAL FORENSICS**, off the critical path (candidate
  `23daf1b4c91d`; not needed to solve F1).

**SOLVED (was the long-standing blocker):** EasyMesh Search/onboarding, WSC M2 transport,
and M2 processing on the extender — via the backhaul WDS-defer fix (rdk-wifi-libhostap 0003/0004 +
rdk-wifi-hal 0023; see #3), validated end to end on the clean rev140 deploy.

**ENCODE FIX IMPLEMENTED + VALIDATED (2026-08-13/14).** Applied the B+C design (WPA2 backhaul +
SAE only on 6 GHz):
- **Fix B** — `unified-wifi-mesh` `0011`: the controller's 6 GHz WSC-M2 auth-upgrade guard
  (`em_configuration.cpp:5277`) now also matches `EM_AUTH_WPA2PSK` (`0x20`) → the 6 GHz M2 is
  upgraded to WPA3/SAE (6 GHz only; 2.4/5 GHz + backhaul stay WPA2).
- **Fix C** — `ccsp-one-wifi-libwebconfig` `0002` (the recipe that actually builds the agent's
  `libwifi_webconfig.so` — *not* `ccsp-one-wifi`): the per-radio M2 apply now sets
  `security.encr = AES/CCMP` (was stale GCMP-256) + `PMF=Required` for WPA3, in **both** the AP
  and STA (`mesh_sta`) branches.
- **Validated** by hot-swapping both binaries into the running lab (preserving the `sta_4addr`
  backhaul fix + onboarding): **all 3 fronthaul subdocs now `encode success`** (was 0/3), the
  6 GHz `radio … not configured` spam **stopped** (OneWifi applied the config), and
  `wifi_hal_setRadioOperatingParameters` is **now reached for all radios incl. 6 GHz (ch37 / op
  class 131 / 6135)** — never reached before. Backhaul (`wifi1.3`) stayed WPA2/stable.
- **Historical hot-swap observation — superseded by the clean rev140 deployment.** On the
  timing-lucky hot-swap run the fronthaul AP VAPs appeared not to bring up: with the config applied,
  `setRadioOperatingParameters` PASS (all 3 radios) but `wifi_hal_createVAP` did the **full create only
  for `mesh_sta_5g`** (the backhaul STA, idx 15); the fronthaul AP VAPs went `pre-create → post-create`
  with no full-create, so their netdevs stayed `down`. (`nl80211_enable_ap`'s `-2 (ENOENT)` was on the
  STOP_AP path = benign; "no `hostapd` process" was not causal — the working controller runs 0 `hostapd`
  too, embedded libhostap.) **The clean rev140 deployment subsequently proved fronthaul AP bring-up
  succeeds** (private_ssid AP up on wifi0/1/2 incl. 6 GHz `wifi2`), so this skipped-full-create was a
  state/timing artifact of the hot-swap, not a surviving product failure.

**CLEAN rev140 B+C BUILD + DEPLOY (2026-08-14).** Build host moved to **rev140** (Ubuntu 20.04
native, the git source-of-truth layer); **rev120 is now the run target only** (7.0 kernel).
Resolved the conflict between the earlier `cffd4f0` "WPA3-everywhere when `HWSIM_6GHZ_CAPABLE`"
seed-gate and the chosen B+C design by **reverting cffd4f0** (0005/0007 → WPA2 defaults under
hwsim regardless of 6 GHz-capable; seed always WPA2 — the 6 GHz guard now handles the fronthaul
upgrade). Built both images clean on rev140 (`HWSIM_6GHZ_CAPABLE=1`, shared sstate) — image seed
verified `WPA2 Personal`/`Optional` ×5. Deployed **both** nodes on rev120 from the rev140 images.
Findings: (a) rev120-ctrl + rev140-ext gave a PMF **status-31** ("Robust Management frame policy
violation") — a cross-build mismatch, **resolved** by deploying the controller from rev140 too
(auth+assoc → status 0). (b) With **both** rev140, the backhaul regressed to **reason-15 4-way
timeout** — see below.

**BACKHAUL / ONBOARDING — FULLY ROOT-CAUSED: a 4-addr trade-off on `mac80211_hwsim`.** The
`rdk-wifi-hal` and `unified-wifi-mesh` patch lists are **identical** rev140 vs rev120 — so this is
not a patch regression. Correcting an earlier note: `sta_4addr_mode_enabled` **is** consumed — by
the HAL (`rdk-wifi-hal/src/wifi_hal.c:1394` `get_sta_4addr_status` reads it from
`/nvram/EasymeshCfg.json` and sets `interface->u.sta.sta_4addr` on the **extender's bSTA** at
VAP-create). So the **extender's** setting is the lever, not the controller's (`dm_device.cpp:382`
hardcodes it `true` on regen — that's the "revert" seen). The trade-off, both sides proven on the
rev140 lab:

```
ext sta_4addr = TRUE   bSTA is 4-addr → its M2 (first 4-addr frame) fires kernel
                       NL80211_CMD_UNEXPECTED_4ADDR_FRAME → HAL wifi_hal_nl80211.c:2631
                       sets wds_sta=1, hostapd creates WDS netdev wifi1.1.sta1 enslaved to
                       brlan0 — BEFORE authorization (authorized=0)
                         → M4 then routes to the WDS netdev, not hostapd EAPOL-RX
                         → controller recv_data_frame gets M2, never M4 → reason-15
                       (rev120 "worked" = TIMING: M4 occasionally beat the WDS routing.)

ext sta_4addr = FALSE  M4 reaches hostapd → controller logs "received eapol m4" → 4-way
                       COMPLETES, bSTA holds (0 reason-15/30 s)  ✓
                         BUT bSTA wifi1.3 is a plain 3-addr STA → NOT in brlan0 (confirmed:
                         brlan0 members = eth1_virt_end wifi0 wifi1 wifi2)
                         → the 1905 autoconfig SEARCH can't cross the backhaul
                         → controller onboards only its colocated agent (al mac 00:00:20),
                           never the extender (al mac cb:61:bf) → no M2 → no encode → fronthaul down
```

**Neither toggle alone works: 4-addr is *required* for the 1905 data-path bridging, but 4-addr
*breaks* the EAPOL 4-way** because the HAL creates the WDS netdev on the first 4-addr frame (M2),
before the STA is authorized, diverting M4. **Fix (implemented + validated): defer the WDS-STA
netdev setup until `WLAN_STA_AUTHORIZED`, then create it from the HAL.** Two parts:
- `rdk-wifi-libhostap` **0003/0004** — hostapd no longer creates the WDS netdev at association
  (`handle_assoc_cb`) or on the first 4-addr frame (`ieee802_11_rx_from_unknown`); both are gated on
  `WLAN_STA_AUTHORIZED` (the flag is still marked early so nothing is lost).
- `rdk-wifi-hal` **0023** — creates the WDS netdev from the HAL `SET_STATION(authorized)` path, which
  is the **reliable** trigger: a WDS netdev left over from an earlier association (the hwsim phy
  outlives an LXD container) otherwise suppresses `UNEXPECTED_4ADDR`, so the station would 4-way but
  never regain a bridge port (`wifi1.1.sta1 master=none`). Gated on a Multi-AP backhaul BSS.

**Validated on the clean rev140 deploy** — both sides of the trade-off hold, in exact order on the
controller HAL log:
```
recv_data_frame: ... received eapol m4                            (4-way completes)
Set STA flags ... authorized=1                                    (STA authorizes)
wifi_drv_sta_set_flags:14814: STA ... authorized on backhaul wifi1.1 -- setting up 4-address WDS aid=1 bridge=brlan0   (0023)
wifi_drv_set_wds_sta:14693: new interface:wifi1.1.sta1 is created with 4addr:1                                         (created + enslaved)
```
0 reason-15; `wifi1.1.sta1 master=brlan0 oper=up`; extender onboards (DeviceList 1→2, BSSList 10→20);
per-radio WSC M2 applied; **fronthaul `private_ssid` AP up on wifi0/1/2, including 6 GHz `wifi2`
(ch 227 / 6135 MHz).**

**OneWifi-restart config replay — ROOT-CAUSED + FIXED + VALIDATED.** A bare `systemctl restart
onewifi` on the extender restored the backhaul/onboarding state (DeviceList=2, WDS bridged into
`brlan0`) but left the M2-derived fronthaul configuration un-replayed — the fronthaul VAPs stayed down
until `em_agent` was restarted. **Root cause:** OneWifi holds its VAP config only in memory; em_agent
pushes it over the RBUS webconfig SOUTH channel as WSC M2s are applied. On restart OneWifi comes back
with every subdoc at version 0 and signals the WebConfig framework to re-push
(`check_component_crash` → `notifyVersion_to_Webconfig` → `rbus_set(webconfigSignal)`). Those helpers
live in the RDK **WebConfig-framework library**, and this EasyMesh image ships **no WebConfig-framework
daemon** to answer them — the set fails `Entry not found` (seen in `WiFilog`), and em_agent (the actual
config source here) neither registers that signal nor observes the restart, so nobody re-pushes.
**Fix** (`unified-wifi-mesh.bbappend`, extender variant only): `em_agent.service PartOf=onewifi.service`,
so an `onewifi` restart propagates to em_agent, whose existing ExecStartPre waits for the backhaul to
reassociate + rebridge and which then re-drives onboarding → M2 → the SOUTH push. **Validated on a
clean lab:** fresh deploy brings fronthaul up (no regression), and `systemctl restart onewifi` alone
(no manual em_agent) **auto-recovers wifi0/1/2 incl. 6 GHz in ~36 s** (m2-recv grows, VAPs UP).
*Characteristic:* the fix restores via a full em_agent re-onboard, so it depends on a healthy
controller re-sending M2 (proven on a clean controller; a controller whose mesh state is stale from
many extender-only redeploys may not re-send M2 — that is a separate controller-state issue). A lighter
in-place "replay the cached subdoc without re-onboarding" would be a future em_agent code refinement.

**Active — next:**
1. **Spare backhaul-AP VAP slots `wifi0.1`/`wifi1.1` are down** (empty SSID) — the extender brings up
   its downstream backhaul AP only on `wifi2.1`. Confirm this is the intended single-radio-backhaul
   layout rather than a missed VAP, before calling the VAP matrix complete.
2. **Not yet tested (completeness):** a client on the extender's own *downstream* 6 GHz backhaul-AP
   `wifi2.1`, and data throughput past the SAE association.

**Completed — 6 GHz SAE-H2E / PMF end-to-end acceptance (PASSED).** The extender's `wifi2` 6 GHz
fronthaul (`private_ssid`, BSSID `02:00:00:5d:4a:88`, 6135 MHz) beacons `Authentication suites: SAE` +
`MFP-required`, and a `wpa_supplicant` client (`sae_pwe=1` H2E, `key_mgmt=SAE`, `ieee80211w=2`)
associated: `wpa_state=COMPLETED`, `key_mgmt=SAE`, `pmf=2`, `mgmt_group_cipher=BIP`, key negotiation
completed; the extender's `iw dev wifi2 station dump` shows the client authorized+authenticated.

**Completed (this investigation):**
2. **6 GHz M2 discriminator — DONE (passes).** Per-radio M2s are sent, including to the
   6 GHz RUID `a8:3b:1c` (`analyze_m2_tx` + `em_state_ctrl_wsc_m2_sent`). So the 6 GHz radio
   *does* get an M2.
3. **[COMPLETED — encode ROOT-CAUSED + FIXED by B+C; retained for provenance, pre-B+C]
   Post-M2 private-subdoc encode failure.** After
   `analyze_m2ctrl_configuration` + `handle_encrypted_settings`, the agent fails at
   `dm_easy_mesh_agent.cpp:1329 "Private subdoc encode failure"` → no config-commit /
   `setRadioOperatingParameters` / START_AP → VAPs down; `radio a8:3b:1c … not configured,
   ignoring` (downstream: the radio never reaches `em_state_agent_onewifi_bssconfig_ind`).
   Captured the real cause by enabling the libwebconfig dbg sink (`touch
   /nvram/wifiWebConfigDbg` → all `WIFI_WEBCONFIG` levels go to `/tmp/wifiWebConfig`). The
   `translate_..._to_vap_per_radio` step **succeeds**; the encode fails one layer later in
   **`encode_security_object`** (`ccsp-one-wifi/source/webconfig/wifi_encoder.c`) because the
   security the M2 provisions is a mismatched pair — **WPA2-Personal (mode `0x10`) +
   AES-GCMP-256 (encr `4`)**:
   - 6 GHz (`encode_security_object:1160`): WPA2 is **illegal** on 6 GHz (must be
     WPA3-Personal/SAE, Enhanced-Open, or WPA3-Enterprise) → `Security object encode failed
     for private_ssid_6g`.
   - 2.4/5 GHz (`:1280`): `is_valid_encr_for_mode(wpa2_personal, aes_gcmp256)` = false →
     `Security object encode failed for private_ssid_2g`.
   This is **band- and role-agnostic** (extender **and** controller-colocated agent, all 3
   radios, 0/3 each) and **unifies the two branches**: the earlier "6 GHz M2 content looks
   wrong (`authtype=20`/WPA2)" *is* what breaks the encode. **Origin traced end-to-end** to the
   controller's M2 build (`em_ctrl.log`): the live NetworkSSIDList carries `"WPA2 Personal"` for
   every SSID/band (incl the 6 GHz radio) → `get_Auth_type_hex` = `EM_AUTH_WPA2PSK` (`0x20`) →
   the 6 GHz auto-upgrade guard at `em_configuration.cpp:5277` tests the wrong constant
   (`EM_AUTH_WPA2` `0x10` ≠ `0x20`) so it never upgrades → M2 authtype `0x20` all bands → agent
   `translate_auth_type_from_easymesh` → `wpa2_personal`, with `encr` left at the stale decoded
   GCMP-256. **Writer of the WPA2 live state — FOUND**: `setup_mysql_db_post.sh` seeds
   `NetworkSSIDList.AuthType='WPA2 Personal'` for every haul (runs when the table is empty);
   `Reset.json`/WPA3 is a separate manual `em_cli` path, not the boot default — which is why
   the live model is WPA2 (DB row confirmed). **Three fixes, ranked:** (1, architectural) fix
   the seed so the live NetworkSSIDList carries the intended **WPA3** policy — aligns the M2
   with the controller's configured 6 GHz policy; (2, latent correctness) fix the
   `EM_AUTH_WPA2` vs `EM_AUTH_WPA2PSK` 6 GHz guard (`em_configuration.cpp:5277`) — worth fixing
   even if #1 makes it dormant; (3, latent correctness) make the agent always set
   `security.encr` coherently with `security.mode` — stale GCMP-256 can break 2.4/5 GHz even
   when the M2 auth is legal. Then confirm config-apply → START_AP → netdevs UP, and `wifi2`
   SAE/PMF.
3. **6 GHz SAE/PMF content — folded into #2** (same defect): fix (A) makes the 6 GHz M2 carry
   SAE, which both satisfies the #3 goal and lets the subdoc encode.
4. **6 GHz security acceptance — PASSED** (clean rev140 deploy):
   ```
   wifi2 beacon                               SAE + MFP-required
   SAE-H2E client association                 PASSED
   PMF                                        Required / pmf=2
   management group cipher                    BIP
   AP station state                           authorized + authenticated
   ```

**Issue F1 — 2nd/3rd-radio bring-up regression — CLOSED.** OneWifi/HAL sequencing
(a standalone channel-set that 7.0 rejects while a sibling AP is active) + wide-channel
defaults; resolved on 7.0 today by 0022 (drive the channel through AP-start) + 0008
(20 MHz clamp). The discriminator proved the kernel brings up multiple 20 MHz channels
on one phy — F1 is **not** a kernel limitation, not MLO/EHT, not channels-count, not a
same-netdev/wiphy-global bug. **Result: 2.4 + 5 GHz concurrent, proven.**

**Issue F2 — 6 GHz AP regulatory blocker — CLOSED.**

```
Cause:
  platform default-country hook absent
      -> wifi_hal_get_default_country_code() error
      -> init_radio_config_default() retains the US fallback
      -> OneWifi applies country US
      -> wireless-regdb US 6 GHz is PASSIVE / NO_IR
      -> cfg80211_reg_check_beaconing() rejects wifi2 START_AP
      -> -EINVAL
Fix:
  under HWSIM_RADIO, 0008c defaults the country to GB (a 6 GHz-IR domain)
Acceptance (real OneWifi, fresh bring-up):
  core reg GB   6135 IR-capable   wifi0.1 UP   wifi1.1 UP   wifi2.1 UP
Result:
  tri-band (2.4 + 5 + 6 GHz) concurrent OneWifi AP operation on one hwsim phy, Linux 7.0
```

Ruled out for the observed 20 MHz F2 failure: hwsim concurrency, context-count,
channel-37/6135 specifics, op-class 134-vs-20, and width; **not tested / not required:**
concurrent 160 MHz 6 GHz capability. The fix is a regulatory provisioning/configuration
change — no wireless-kernel capability or HAL channel-path change. Because only the
default country changed (US→GB) on the identical OneWifi state-machine + HAL channel path,
the causal chain is proven end-to-end with no second downstream defect. The later EasyMesh work
root-caused the backhaul failure as **WDS creation before authorization** and fixed it by deferring
WDS-STA setup until `WLAN_STA_AUTHORIZED` (rdk-wifi-libhostap 0003/0004) and creating the netdev from
the HAL `SET_STATION(authorized)` path (rdk-wifi-hal 0023). Security provisioning/encoding was also
corrected by B+C. On the clean rev140 deployment onboarding, per-radio M2 application, tri-band
fronthaul AP bring-up, and the 6 GHz SAE-H2E/PMF client acceptance all pass.

Status:

```
F1a channel-set sequencing                              CLOSED
F1b 5-GHz wide-channel default                          CLOSED
2.4 + 5 GHz concurrent                                  PROVEN

F2  observed wifi2 -EINVAL  ROOT-CAUSED + FIXED (acceptance PASSED)
  OneWifi/HAL default country -> US                     PROVEN (HAL US fallback)
  US -> 6-GHz NO_IR                                     PROVEN (regdb US 6 GHz = PASSIVE)
  NO_IR -> cfg80211 START_AP -EINVAL                    PROVEN (cfg80211_reg_check_beaconing)
  6135/20 under IR, alone                               PROVEN (matrix B)
  6135/20 under IR, as 3rd concurrent AP                PROVEN (matrix D)
  fix: 0008 default country -> GB under HWSIM_RADIO     BUILT + DEPLOYED
  real OneWifi tri-band 2.4+5+6 GHz concurrent AP-UP    PASSED (real OneWifi path in RDK container)
  concurrent 160 MHz 6 GHz capability                  NOT TESTED / not required
  tri-band re-proven on a fresh -F controller boot     PROVEN

#3 controller live VAP policy (its own radios)          PROVEN (WPA3-Personal + MFP Required)
#3 extender 6-GHz regulatory readiness                  PROVEN (core GB, 6135 IR on extender)
WSC M2 transport / delivery / parsing / application     PROVEN (clean rev140 acceptance applied M2 through to fronthaul AP-UP)
6-GHz RUID receives/parses M2                           PROVEN
6-GHz RUID M2 contains 3 BSS                            PROVEN (private_ssid/mesh_backhaul/iot_ssid)

SECURITY PROVISIONING
  live NetworkSSIDList = "WPA2 Personal" (all SSIDs)    PROVEN (em_ctrl.log:5273; DB row confirmed)
  writer of that live state                            PROVEN — setup_mysql_db_post.sh DB seed (hardcodes
                                                          AuthType='WPA2 Personal'; runs when table empty;
                                                          Reset.json/WPA3 is a separate manual em_cli path)
  NetworkSSIDList feeds M2 auth                        PROVEN
  M2 auth = EM_AUTH_WPA2PSK (0x20)                     PROVEN (all bands)
  6-GHz upgrade guard misses 0x20                      PROVEN BUG (em_configuration.cpp:5277 tests
                                                          EM_AUTH_WPA2 0x10; "WPA2 Personal"->0x20 -> no upgrade)
  agent maps auth -> WPA2-Personal (mode 0x10)         PROVEN (translate_auth_type_from_easymesh)
  agent leaves cipher stale = GCMP-256 (encr 4)        PROVEN BUG (per-radio block sets mode, not encr)

ENCODE
  input tuple = WPA2-Personal + GCMP-256              PROVEN
  encoder rejection (encode_security_object)          ROOT-CAUSED
    6-GHz WPA2 rejection                              PROVEN (wifi_encoder.c:1160, needs WPA3/SAE)
    2.4/5 tuple rejection                             PROVEN (is_valid_encr_for_mode(WPA2,GCMP256)=false, :1280)
  failing call chain                                  PROVEN (webconfig_easymesh_encode(vap_XG) ->
                                                          translate_..._to_vap_per_radio [OK] -> encode_multivap_subdoc
                                                          -> encode_private_vap_object -> encode_security_object [FAILS])
  reproduced on extender AND ctrl-colocated agent     PROVEN (0 success / 3 fail each)

FIXES (B+C) + POST-FIX VALIDATION (hot-swap)
  Fix B: 6-GHz guard matches EM_AUTH_WPA2PSK          IMPLEMENTED (unified-wifi-mesh 0011)
  Fix C: coherent cipher/PMF, AP + STA branches       IMPLEMENTED (ccsp-one-wifi-libwebconfig 0002)
  private-subdoc encode                               PASSED 3/3 (was 0/3)
  config reaches OneWifi (applied)                    PROVEN ("radio not configured" cleared)
  setRadioOperatingParameters                         PROVEN 3/3 (incl 6 GHz ch37/opclass131)
  backhaul (wifi1.3, WPA2)                            UP / stable

CLEAN rev140 B+C BUILD + DEPLOY
  build host moved to rev140 (rev120 = run target)    DONE
  cffd4f0 reverted -> WPA2 seed + WPA2 defaults        DONE (image seed verified WPA2/Optional x5)
  both nodes deployed from rev140 images               DONE

BACKHAUL 4-way (4-addr WDS-before-auth) — FIXED + VALIDATED (clean rev140 deploy)
  ext 4addr=true -> WDS created on 1st 4-addr frame    was the defect (before auth -> M4 diverted -> reason-15)
  ext 4addr=false -> 4-way OK but bSTA un-bridged      the other horn (1905 Search can't cross)
  fix pt1: defer WDS setup until WLAN_STA_AUTHORIZED   DONE (rdk-wifi-libhostap 0003/0004)
  fix pt2: create WDS from HAL SET_STATION(authorized) DONE (rdk-wifi-hal 0023; reliable trigger --
                                                        a leftover WDS netdev suppresses UNEXPECTED_4ADDR)
  4-way completes (M4 received), 0 reason-15           PROVEN (extender stays 4-addr)
  WDS created at auth (0023 log line, in order)        PROVEN (wifi_drv_sta_set_flags:14814 -> set_wds_sta:14693)
  wifi1.1.sta1 enslaved to brlan0                      PROVEN (master=brlan0 oper=up)

ONBOARDING + FRONTHAUL — VALIDATED (clean rev140 deploy, end to end)
  1905 autoconfig Search crosses backhaul             PROVEN (extender onboards)
  controller models the extender                      PROVEN (DeviceList 1->2, BSSList 10->20)
  per-radio WSC M2 applied (private/mesh_bh/iot)       PROVEN ("Authenticator verification succeeded")
  fronthaul private_ssid AP up on wifi0/1/2            PROVEN (state=up, type AP)
  6 GHz fronthaul AP (wifi2)                           UP (ch 227 / 6135 MHz, 23 dBm, both nodes)
  wifi2 SAE-H2E + PMF client acceptance               PASSED (beacon SAE+MFP-required; client
                                                        key_mgmt=SAE, pmf=2, BIP, wpa_state=COMPLETED)

Post-onboarding                                         VALIDATED
  per-radio M2 to 6-GHz RUID                           PROVEN
  M2 security corrected by B+C                         PROVEN
  private-subdoc encode                                PASSED
  OneWifi config apply                                 PASSED
  fronthaul private_ssid AP wifi0/1/2                  UP
  wifi2 6-GHz AP @ 6135                                UP

#3 acceptance (6 GHz SAE-H2E + PMF) — PASSED:
  extender wifi2 beacon RSN (6135)                    SAE + MFP-required
  client SAE-H2E association to wifi2 (5d:4a:88)       PASSED (key_mgmt=SAE, wpa_state=COMPLETED)
  PMF Required observed end-to-end                     PASSED (pmf=2, mgmt_group_cipher=BIP)
```

## #3 — controller → WSC M2 → extender 6 GHz SAE/PMF (validated end to end; acceptance PASSED)

Controller→M2→extender 6 GHz provisioning, fronthaul AP bring-up, and the SAE-H2E + PMF client
acceptance are all validated. Fix B produces the 6 GHz WPA3/SAE M2 security, Fix C produces a
coherent cipher/PMF configuration, the clean rev140 run brings the extender's 6 GHz fronthaul AP up at
6135 MHz beaconing `Authentication suites: SAE` + `MFP-required`, and a `wpa_supplicant` SAE-H2E
client associated to it (`key_mgmt=SAE`, `pmf=2`, `mgmt_group_cipher=BIP`, `wpa_state=COMPLETED`; the
extender's station dump shows it authorized+authenticated). See the top *#3 evidence boundary* /
*Completed — 6 GHz SAE-H2E / PMF acceptance* block for the exact evidence.

**Controller-side 6 GHz security policy — PROVEN.** The final B+C design **deliberately reverted** the
earlier `cffd4f0` "WPA3-everywhere when `HWSIM_6GHZ_CAPABLE`" seed gate. The boot `NetworkSSIDList` is
**intentionally seeded WPA2 Personal / MFP Optional** (backhaul and 2.4/5 GHz stay WPA2-PSK); **Fix B**
performs the `WPA2PSK → WPA3/SAE` upgrade **for the 6 GHz RUID only, during WSC-M2 construction**, and
**Fix C** on the agent makes the applied config coherent (mode WPA3-Personal, cipher AES/CCMP, PMF
Required). The result is confirmed on the wire: a station scan shows the controller's own 6 GHz VAPs
beaconing SAE + MFP-required:

```
private_ssid  (6135, ctrl RUID)   Authentication suites: SAE   MFP-required   (SAE-H2E + mandatory PMF)
mesh_backhaul (6135, ctrl RUID)   Authentication suites: SAE   MFP-required
```
**Scope of this proof.** The controller's own live 6 GHz VAP policy is WPA3-SAE + MFP Required (scan-confirmed).
Generic WSC M2 **delivery and extender parsing** are proven (the extender's
`analyze_m2ctrl_configuration` processes the M2's BSS list), and the controller is proven to
generate/send an M2 addressed to the extender's 6 GHz RUID (`a8:3b:1c`), parsed into three BSS
entries. What earlier looked like two independent branches (controller M2 content vs extender
encode) is now a **single proven causal chain**:

```
PRE-FIX FAILURE CHAIN (pre-B+C -- retained for provenance; fixed below)

live NetworkSSIDList
    "WPA2 Personal"                     (setup_mysql_db_post.sh DB seed; Reset.json/WPA3 is a
        |                                separate manual em_cli path, not the boot default)
        v
get_Auth_type_hex()
    EM_AUTH_WPA2PSK = 0x20
        |
        +-- 6 GHz upgrade guard checks
        |      EM_AUTH_WPA2 = 0x10       (em_configuration.cpp:5277)
        |      -> no match
        |      -> no WPA3 upgrade        <-- latent guard bug
        |
        v
M2 auth = WPA2-PSK  (all bands)
        |
        v
agent translate_auth_type_from_easymesh()
    security.mode = WPA2-Personal
        |
        +-- security.encr NOT refreshed  (per-radio block sets mode, not encr)
        |      -> stale GCMP-256         <-- agent cipher-state bug
        |
        v
encode_security_object()
        |
        X
  6 GHz: WPA2 invalid  (:1160)
  2.4/5: WPA2 + GCMP-256 invalid  (:1280)
```

This was the authoritative *pre-fix* tree; the controller-content and extender-encode facets were the
**same defect**. B+C fixes it and the final security provenance now runs end to end:

```
FINAL SECURITY PROVENANCE (post-B+C, clean rev140 deploy)

boot NetworkSSIDList
    WPA2 Personal                         intentional B+C baseline (backhaul + 2.4/5 GHz stay WPA2)
        |
        v
get_Auth_type_hex()
    EM_AUTH_WPA2PSK
        |
        v
Fix B, 6-GHz RUID only                    em_configuration.cpp:5277 guard now matches WPA2PSK
    WPA2PSK -> WPA3/SAE
        |
        v
WSC M2  (to the extender's 6 GHz RUID)
        |
        v
Fix C on agent
    mode   = WPA3-Personal
    cipher = AES/CCMP
    PMF    = Required
        |
        v
private subdoc encode                     PASS
        |
        v
OneWifi config apply                      PASS
        |
        v
wifi2 @ 6135                              UP  (beacon: SAE + MFP-required)
        |
        v
SAE-H2E + PMF client                      PASS  (key_mgmt=SAE, pmf=2, BIP, wpa_state=COMPLETED)
```

**Extender 6 GHz regulatory readiness — PROVEN.** Rebuilt the AP/extender image with 0008c
(`cleansstate ccsp-one-wifi` in `build-qemux86bpiap`; image `X86EMLTRBPIAP_…204122`) and
deployed `bpiap-001` (`HWSIM_CHANNELS=3 ./bpi.sh <ap> -i 1 -F`, single phy). It boots with
**core reg GB, 6135 IR-capable (23 dBm)** — so the former F2 regulatory blocker is absent
on the extender. That regulatory-readiness boundary was subsequently closed: on the clean rev140
deployment `wifi2` comes **UP at 6135 MHz** and passes **SAE-H2E/PMF client acceptance** (see #3).

**Historical rev120 timing-lucky onboarding — SUPERSEDED by the clean rev140 A/B (see the
*CLEAN rev140 B+C BUILD + DEPLOY* section).** *The earlier conclusion that the controller-side
`sta_4addr_mode_enabled=false` setting fixed the backhaul was **incorrect**.* The clean rev140
investigation shows the **controller value is effectively a no-op** for this path; the
**extender bSTA's 4-addr setting is the causal lever**, and it only trades the 4-way against the
bridged data path (a WDS-before-authorization race). Intermittent rev120 onboarding occurred
because **M4 sometimes won the race against WDS setup**. The evidence trail below describes that
timing-lucky rev120 run (M4 absent from `recv_data_frame` under 4-addr → reason-15; the 4-way
then *sometimes* holding and M2 reaching `analyze_m2ctrl_configuration`) — retained for
provenance, but the authoritative current state is the clean rev140 A/B.

Direct instrumentation (host `strace` + `nsenter tcpdump` + `iw event` + EAPOL decode + the
AP's HAL log) localized the original failure to the **mesh-backhaul WPA2-PSK 4-way
handshake**: the STA transmits a structurally correct M4 onto the link, but the **controller
AP's authenticator does not process/accept it and never advances past M3**, timing out
(deauth reason 15). Credentials are ruled out (M2 MIC accepted → compatible PMK/PTK). An
AP-side EAPOL-RX probe showed **M4 never reaches the AP's EAPOL handler** under 4-addr
(`recv_data_frame` logs m2,
never m4; M4 on the wire) — a delivery/interface problem. **At the time this run appeared fixed when
the controller `sta_4addr_mode_enabled` was changed to `false`** — the 4-way then completed (0
reason-15/40 s), the extender **onboarded** (controller data-models it; 3 devices), and the
controller's **WSC M2 was delivered and processed** (4 BSS) — **but that result was later shown to be
timing-dependent rather than causal** (the controller value is a no-op for this path; see the
superseding paragraph above and the clean rev140 WDS-defer fix). The genuine fix is deferring WDS-STA
setup until authorization (rdk-wifi-libhostap 0003/0004 + rdk-wifi-hal 0023). (At *this* stage the capture appeared to carry no 6 GHz VAP; that was later
**disproven** as a capture-selection artifact — per-radio M2s *are* sent to the 6 GHz RUID,
see the post-fix sections below.)

*Proven (both discriminators resolved):*
- **Generic 1905 raw TX works.** `strace` of `ieee1905` shows `sendto(…, 43, …,
  {AF_PACKET, sll_ifindex=19 (eth1_virt_peer), …}) = 43`, and `tcpdump -i any` shows the
  frame egressing **eth1_virt_peer → eth1_virt_end → brlan0**. *(Retires the earlier
  "no egress" artifact — those captures watched `brlan0`/`wifi1.3`, not the real egress
  iface `eth1_virt_peer`.)*
- **Discriminator #1 — Search-specific TX works (PASSES).** The agent had stopped
  searching (bounded ~33 tries, then gives up); restarting `em_agent`/`ieee1905_em_agent`
  re-triggered it (30 searches in-window), and `strace` of `ieee1905` then shows **6×
  `sendto()` of CMDU type `0x0007` (AP-Autoconfig-Search)** with return = full length,
  alongside 3× Topology Discovery (0x0000). So the Searches are **successfully submitted to
  the AF_PACKET TX path** — the Search-specific transmit path is not the gap (controller
  reception was still absent *at that pre-fix stage*, downstream — later resolved by the
  WDS-before-authorization fix described in the clean rev140 section). The first missing boundary
  moves to the backhaul.
- **Discriminator #2 — the backhaul flap is a real 802.11 cycle killed at the key
  handshake.** `iw event` on `wifi1.3`:
  ```
  auth   02:00:00:4a:bb:d0 -> 02:00:00:5d:ee:73  status 0: Successful
  connected to 02:00:00:4a:bb:d0
  deauth 02:00:00:4a:bb:d0 -> 02:00:00:5d:ee:73  reason 15: 4-way handshake timeout
  disconnected (by AP) reason 15: 4-way handshake timeout
  ```
  So a **real 802.11 association forms** (auth OK → connected), then the **WPA2-PSK 4-way
  handshake times out** and the controller AP **deauths (reason 15)** — a ~14 s
  auth→connect→4-way-timeout→deauth loop. The DPP `ec_enrollee` "connected" was masking a
  genuine association that dies at the EAPOL key exchange.

*EAPOL M1–M4 decode + HAL RX instrumentation — failure localized to M4 delivery into the
AP EAPOL-RX path.* Two-sided capture (`nsenter tcpdump` on the STA `wifi1.3` and AP
`wifi1.1`) + the controller's own HAL log:
```
AP  sending eapol m1  replay 1
STA -> AP  M2  key_info=0x0108 (pairwise+MIC)  replay 1     ; AP: "received eapol m2 counter 1"
AP  sending eapol m3  replay 2
STA -> AP  M4  key_info=0x0308 (pairwise+MIC+Secure) replay 2   ; on the wire (tcpdump)
AP  sending eapol m3  replay 3    ; retransmit -- AP NEVER logs "received eapol m4"
… deauth reason 15
```
So: **M2 is accepted** (AP proceeds to M3 → the M2 MIC passed the authenticator → both
sides have compatible PMK/PTK derivation for this association → *not* a credential
problem), and the **STA emits a structurally correct M4 onto the link** (pairwise+MIC+
Secure flags, replay counter 2 matching M3, on the wire — this proves the key-info/replay
*fields*, not that the M4 MIC cryptographically validates at the AP). But **the STA
transmits M4, and the controller AP's authenticator does not process/accept it and
therefore never advances past M3** — it retransmits M3 (replay 3, 4, …) until the 4-way
timeout, with **no `received eapol m4` log**. Immediately *before* M1 the HAL logs
`Set WDS STA … name=wifi1.1.sta1` + `enslave device wifi1.1.sta1` — it creates a
**4-address/WDS STA netdev** (`sta_4addr_mode_enabled=true`). **Leading hypothesis:** after
that WDS setup the STA's post-association EAPOL (M4) is diverted to the WDS netdev
`wifi1.1.sta1` (enslaved to `brlan0`) rather than reaching hostapd's EAPOL RX on `wifi1.1`.

*First failing boundary — M4 delivery into the AP EAPOL-RX path.*
```
PROVEN:
  STA generates M4 with expected key-info/replay fields
  M4 is visible on the AP-side wireless packet path (tcpdump on wifi1.1)
  recv_data_frame receives M2 but never M4
THEREFORE:
  M4 is lost/diverted before the HAL EAPOL-RX handler (recv_data_frame)
  MIC / replay / authenticator-state processing of M4 is NEVER REACHED (downstream)
```
**Ruled out:** credentials (M2 MIC accepted → compatible PMK/PTK). The AP then retransmits
M3 until deauth reason 15. In that pre-fix run, because the backhaul did not hold, the
autoconfig-searches (proven submitted to the AF_PACKET TX path) never completed with the
controller → no data-model → no M2 → extender fronthaul (incl. `wifi2`) down. *(All of this
was later resolved by the WDS-before-authorization fix described in the clean rev140 section; the
backhaul now holds and the M2 is delivered.)*

*A/B on `sta_4addr_mode_enabled` — WDS-diversion hypothesis NOT supported (weakened).* Set
`false` on the extender + restarted the agent. A clean `iw event` tally still shows the
**same failure: reason-15 4-way timeout (4 deauths / 3 connects in 45 s)** — the backhaul
keeps flapping. (An earlier operstate-only sample showed a stable 45 s window, but that was
a **polling artifact** — sampling caught brief connected phases; the event tally is
authoritative.) Caveat: the controller **still created the WDS netdev `wifi1.1.sta1`** with
the extender's 4-addr off, so the extender-side toggle did **not** actually remove
controller-side WDS — the test is therefore not fully clean. Net: this does **not** confirm
4-addr/WDS as the cause and weakens it; the decisive next test is the **AP-side EAPOL-RX
callback probe**, not a config toggle.

*AP-side EAPOL-RX probe — the fork is RESOLVED to the delivery/interface branch.* The
controller HAL logs its EAPOL receive path (`recv_data_frame:3202: … received eapol mN`).
Over 35 s / 2 handshake attempts it logged **2× "received eapol m2" and ZERO "received
eapol m4"** (while sending 2× m1 + 8× m3 retransmits). So:
```
STA M4 (on the link)
 +-- absent at the AP EAPOL-RX handler     -> DELIVERY / INTERFACE path   <== THIS (m2 seen, m4 never)
 +-- present at the handler, no advance    -> station-lookup / MIC / replay / state (excluded)
```
**M4 reaches the wire but not the AP authenticator's receive handler.** This **re-elevates
WDS** as the leading *delivery-path* candidate: the controller-side WDS netdev
`wifi1.1.sta1` (created after association, still present) most likely captures the
post-association M4 data frame and bridges it into `brlan0` instead of delivering it to
hostapd's EAPOL RX on `wifi1.1`. It also explains why the **extender-side** 4-addr A/B did
not help — it never removed the **controller-side** WDS object. **Next decisive test:
disable WDS on the controller/authenticator side** and re-check whether `recv_data_frame`
then logs `received eapol m4` and the 4-way completes.

*Historical misleading A/B — initially interpreted as controller-side causal; later disproven by
clean rev140 testing.* Setting `sta_4addr_mode_enabled=false` on the controller + restarting its
OneWifi (F2 tri-band restored — wifi0/1/2 up) *appeared* to unblock the whole chain in this run:
```
backhaul 4-way completes/holds     seen (iw event: 0 reason-15 / 40 s)
extender onboards (1905 topology)  seen (ctrl: "Created data model … 02:00:00:00:01:20"
                                          + "Received autoconfig search from … 01:20"; 3 devices)
controller sends WSC M2            seen
extender processes M2              seen (em_agent analyze_m2ctrl_configuration:
                                          4 BSS -- private_ssid/mesh_backhaul/iot_ssid/lnf_radius)
```
**This "controller `sta_4addr` is the causal lever" reading was later shown to be wrong.** The clean
rev140 A/B established that the controller value is **effectively a no-op** for this path — the
controller still creates `wifi1.1.sta1` regardless — and that the real defect is **WDS creation before
authorization** (the extender's bSTA is 4-addr, so its M4 is diverted to the WDS netdev before the
authenticator sees it). The intermittent success here was **timing-dependent** (M4 occasionally beat
the WDS setup), not caused by the controller toggle. The genuine fix defers WDS-STA setup until
`WLAN_STA_AUTHORIZED` and creates it from the HAL `SET_STATION(authorized)` path (see the clean rev140
section). (Also, because the `iw event` sampled an already stable link, no fresh `received eapol m4`
was captured in *this* run.)

**Historical pre-B+C post-onboarding boundaries — superseded.**
- **6 GHz M2 discriminator — PASSES (6 GHz radio *does* get an M2).** The extender's RUIDs
  are `da:33:84` (2.4), `9b:17:d3` (5), `a8:3b:1c` (6 GHz); the controller `em_ctrl` logs
  `analyze_m2_tx: Radio: …a8:3b:1c` and `em_state_ctrl_wsc_m2_sent radio mac:…a8:3b:1c` —
  i.e. **per-radio M2s are sent, including to the 6 GHz RUID**. The earlier "M2 had no
  6 GHz VAP" was a capture artifact (that snippet was the 5 GHz radio `9b:17:d3` only).
- **Fronthaul-activation discriminator — first missing transition is a concrete error.**
  The extender **parses M2** (`analyze_m2ctrl_configuration` ×10, all radios incl. the
  6 GHz RUID `a8:3b:1c` — 3 BSS: private_ssid/mesh_backhaul/iot_ssid), then
  `handle_encrypted_settings` runs, but the next step **fails**:
  `dm_easy_mesh_agent.cpp:1329: **Private subdoc encode failure**`. Because the agent can't
  encode the OneWifi "private subdoc" (the config blob that drives VAP bring-up), there is
  **no config-commit, no `setRadioOperatingParameters`, no `update_hostap_iface`/START_AP**;
  the fronthaul VAPs stay `type AP`, down, and `em_configuration.cpp:5878` then logs
  `radio 02:00:00:a8:3b:1c is not configured, ignoring`. So the first missing transition is
  **M2-parsed → OneWifi private-subdoc encode** on the agent.
- **6 GHz M2 content (secondary, to verify after the subdoc blocker):** the M2 to the 6 GHz
  RUID carries the generic `private_ssid` (not `private_ssid_6g`) with `authtype[*]=20`
  (appears WPA2-PSK). Whether the 6 GHz RUID's M2 should encode SAE/PMF (vs the generic
  WPA2 fronthaul) is the #3 content question — but it is moot until the subdoc-encode
  failure is fixed, since no fronthaul VAP is configured at all.

So onboarding + M2 delivery (incl. to the 6 GHz radio) are **solved**; the open work is the
agent's **M2 → OneWifi private-subdoc encode → config-apply** path (the `Private subdoc
encode failure`), after which fronthaul START_AP and the 6 GHz SAE/PMF acceptance can be
verified.

*Clean-redeploy result — REPRODUCIBLE (of the original failure).* A fresh `-F` redeploy of
both nodes re-proved F2 (controller tri-band) and reproduced the reason-15 flap. *(Note: the
"controller 4-addr EAPOL handling" framing here is **PRE-clean-rev140** — since retracted; the
causal lever is the **extender** bSTA 4-addr, a WDS-before-auth race. See the top #3 boundary.)*

> **Net #3 — PRE-B+C / PRE-clean-rev140 snapshot (SUPERSEDED).** Authoritative current state is
> the top *#3 evidence boundary* + *CLEAN rev140 B+C BUILD + DEPLOY* section. Retained for provenance.

- controller policy source: **PROVEN** correct (WPA3/SAE + PMF)
- onboarding / backhaul: ~~SOLVED~~ → **SUPERSEDED** — on the clean rev140 build, blocked by the
  extender-bSTA WDS-before-authorization race (see top)
- per-radio M2 delivery, including 6-GHz RUID: **PROVEN** (on the hot-swap run)
- 6-GHz RUID M2 parsing: **PROVEN**
- agent M2 → OneWifi private-subdoc encoding: ~~FAILS~~ → **FIXED by B+C** (root-caused here, then
  fixed; all 3 radios 2.4/5/6 encode 3/3). Original defect below, retained for provenance:
- **exact cause PROVEN**: encode succeeds through `translate_..._to_vap_per_radio` but fails in
  `encode_security_object` (`wifi_encoder.c`) — the M2 provisions **WPA2-Personal (mode 0x10) +
  AES-GCMP-256 (encr 4)**, which is rejected: 6 GHz → WPA2 illegal (`:1160`); 2.4/5 GHz →
  `is_valid_encr_for_mode(WPA2,GCMP256)`=false (`:1280`)
- **branches unified**: the "6-GHz M2 content looks wrong (`authtype=20`/WPA2)" and the
  "encode fails" are the **same defect** — the WPA2 security in the M2 is what breaks the encode
- **origin TRACED (3 defects)**: (1) **controller seed [writer PROVEN]** — the live
  NetworkSSIDList is `"WPA2 Personal"` for every SSID/band incl 6 GHz (`em_ctrl.log:5273` + DB
  row), written by `setup_mysql_db_post.sh` which hardcodes `AuthType='WPA2 Personal'`
  (`Reset.json`/WPA3 is a separate manual `em_cli` path, not the boot default); (2)
  **controller code [latent bug]** — the 6 GHz auto-upgrade guard (`em_configuration.cpp:5277`)
  tests `EM_AUTH_WPA2` (`0x10`) while `"WPA2 Personal"`→`EM_AUTH_WPA2PSK` (`0x20`), so 6 GHz is
  never upgraded to WPA3; (3) **agent code [latent bug]** — the per-radio block sets
  `security.mode` from the M2 authtype but never sets `security.encr`, leaving stale GCMP-256 →
  invalid pair on 2.4/5 GHz
- config apply / START_AP / `wifi2` SAE+PMF: ~~NOT REACHED~~ → **REACHED on the clean rev140 deploy**
  (fronthaul APs incl. `wifi2` 6 GHz up; SAE-H2E/PMF *client* association subsequently PASSED —
  see current #3 acceptance)

The chain traces to a single runtime point. The backhaul 4-way failed because the AP EAPOL-RX
handler never received M4 (`recv_data_frame` logs m2, never m4; M4 on the wire) → reason-15 — the
extender's bSTA is 4-addr, so the HAL created the WDS netdev before authorization and M4 was diverted
to it. **Fixed** by deferring WDS-STA setup until `WLAN_STA_AUTHORIZED` (rdk-wifi-libhostap 0003/0004)
and creating it from the HAL `SET_STATION(authorized)` path (rdk-wifi-hal 0023) — *not* by the earlier
controller `sta_4addr` toggle, which was timing-dependent. With the fix the 4-way completes (0
reason-15), the extender **onboards** (controller data-models it), the controller **sends per-radio
M2s including to the 6 GHz RUID `a8:3b:1c`**, and the extender **parses and applies M2**
(`analyze_m2ctrl_configuration`, 6 GHz RUID gets 3 BSS). So onboarding + M2 delivery/application
(incl. 6 GHz) are **solved**. At this pre-B+C stage, the agent's **M2 → OneWifi private-subdoc
encode** was the first failing boundary (`dm_easy_mesh_agent.cpp:1329 "Private subdoc encode
failure"`), so no fronthaul VAP was configured/START_AP'd. It was subsequently **fixed by B+C**; the
clean rev140 deployment now passes M2 application, fronthaul AP bring-up, and 6 GHz SAE-H2E/PMF client
acceptance. This encode failure (below, retained for provenance) was **universal** —
identical (0 success / 3 fail) on the remote extender agent **and** the controller's own
colocated agent, across all three radios (2.4/5/6) — so it is a **build-wide agent defect**
in the per-radio private-subdoc encode path, not a 6 GHz-content or extender-specific
problem. **Exact cause captured** by enabling the libwebconfig dbg sink (`touch
/nvram/wifiWebConfigDbg` → all `WIFI_WEBCONFIG` levels to `/tmp/wifiWebConfig`): the encode
runs `webconfig_easymesh_encode(vap_XG)` → `translate_..._to_vap_per_radio` (**succeeds**) →
`encode_multivap_subdoc` → `encode_private_vap_object` → **`encode_security_object`
(`wifi_encoder.c`) FAILS**. The security the M2 provisions is a mismatched pair —
**WPA2-Personal (mode `0x10`) + AES-GCMP-256 (encr `4`)** — rejected two ways: on 6 GHz WPA2
is illegal (`:1160`, must be WPA3/SAE), and on 2.4/5 GHz
`is_valid_encr_for_mode(WPA2,GCMP256)` is false (`:1280`). So the "secondary" 6 GHz content
question and this encode failure are the **same defect**: the WPA2 security carried in the M2
(`authtype=20`) is exactly what the encoder rejects. *(Pre-B+C.)* The WPA2+GCMP-256 origin is
now fully traced (writer = `setup_mysql_db_post.sh`; guard-constant bug; agent stale cipher) and
**FIXED** by B+C — the M2 now carries WPA3/SAE on 6 GHz and a coherent cipher on all bands, and
the private subdoc encodes 3/3. See the *#3 evidence boundary* and *ENCODE FIX IMPLEMENTED +
VALIDATED* blocks. B+C subsequently fixed this encode defect, and the WDS-defer fix allowed the clean
rev140 deployment to proceed through onboarding and fronthaul AP bring-up. The #3 security acceptance
then passed: `wifi2` beacons SAE + MFP-required and a SAE-H2E client associates end to end
(`key_mgmt=SAE`, `pmf=2`, `BIP`, `wpa_state=COMPLETED`).

## Artifacts (on rev120)

- Tree `/home/rev/yocto/rdkb-bpi-rev120`; build container image `bpi-builder:20.04`
  (Dockerfile in `/home/rev/bpi-builder`); build log `<tree>/build-6g.log`.
- 6 GHz images under each `build-*/tmp/deploy/images/`; controller deployed as LXD
  container `bpibroadband` (still running for inspection).

## Appendix — standalone hwsim 6 GHz VLP-AP verification

Before (and independent of) the RDK stack, the kernel/hwsim side was proven on its
own: can `mac80211_hwsim` bring up a 6 GHz AP on this 7.0 kernel and let a second
hwsim STA associate with SAE-H2E + PMF? This isolates "6 GHz works on hwsim/7.0"
from any OneWifi/RDK behaviour. (Merged here from the former
`Linux-7.0-hwsim-6GHz-VLP-AP-{verification,results}.md`.)

**Environment.** `rev120`, kernel `7.0.0-28-generic` (Ubuntu 24.04.4,
`linux-hwe-7.0`), `CONFIG_MAC80211_HWSIM=m`, Secure Boot disabled, `iw` 6.7.

**Verdict — PROVEN.** A 6 GHz AP on **5975 MHz (channel 5)** reaches hostapd
`AP-ENABLED`, and a second hwsim STA authenticates (SAE-H2E), associates, and
completes the 4-way handshake on 5975. Key nuance: on 7.0 the **stock, unpatched**
module also reaches `AP-ENABLED` there — because `regtest=5` → `custom_03` leaves
all 6 GHz channels **IR-capable (0 NO_IR)**, so no VLP exception is needed to
beacon. The 6.8-era NO_IR blocker does not reproduce under this hwsim custom
domain. (This is exactly the lever the RDK lab uses — see *Setup* above.)

**The modern 6 GHz API is present on 7.0** (absent on the 6.8 run host):
`NL80211_RRF_ALLOW_6GHZ_VLP_AP`, `IEEE80211_CHAN_ALLOW_6GHZ_VLP_AP`,
`IEEE80211_REG_VLP_AP`, `NL80211_FREQUENCY_ATTR_ALLOW_6GHZ_VLP_AP`.

**The VLP-AP patch (optional on 7.0).** One `REG_RULE` change to the `custom_03`
domain, built against the running kernel (`vermagic 7.0.0-28-generic`):

```diff
--- a/drivers/net/wireless/virtual/mac80211_hwsim.c   (hwsim_world_regdom_custom_03)
-	REG_RULE(5955 - 10, 7125 + 10, 320, 0, 33, 0),
+	REG_RULE(5955 - 10, 7125 + 10, 320, 0, 33, NL80211_RRF_ALLOW_6GHZ_VLP_AP),
```

Unlike the 6.8 source, `regtest=5` already maps to `custom_03` on 7.0, so only this
one flag is needed — and it turns out not to be *required* to beacon here (stock
works), only to advertise the standards-correct VLP power type.

**Proven (module `radios=2 channels=1 regtest=5`, `country 99`):**

```
5975.0 MHz [5] (33.0 dBm)                 6 GHz ch5 usable, no NO_IR
6 GHz channels (5955-7125) "no IR": 0

hostapd (channel=5 op_class=131 he_6ghz_reg_pwr_type=2 wpa=2 SAE ieee80211w=2):
  nl80211: Set freq 5975 (he_enabled=1, 20 MHz) -> AP-ENABLED   (type AP, 33 dBm)
wpa_supplicant (sae_pwe=1):
  Associated with 02:00:00:00:01:00 -> WPA: Key negotiation completed [CCMP] -> CONNECTED
  iw dev wlan0 link -> Connected, SSID hwsim-6g-vlp, freq 5975.0
```

**Toolchain requirement.** 6 GHz needs a recent hostapd + wpa_supplicant (≈2.11+):
built `v2.13-devel` from `hostap.git`. The distro **2.10** pair is insufficient —
hostapd lacks `he_6ghz_reg_pwr_type=2` and wpa_supplicant 2.10 reports "No suitable
network found" on a 6 GHz-SAE beacon it can otherwise see. This is a STA-side 2.10
limitation, not an RF/AP failure.

**Rollback.** `modprobe -r mac80211_hwsim && modprobe mac80211_hwsim` restores the
stock module; nothing under `/lib/modules` was replaced. Artifacts on rev120 under
`~/hwsim6-vlp/`.
