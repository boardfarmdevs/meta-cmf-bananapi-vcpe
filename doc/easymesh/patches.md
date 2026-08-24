# Patch Catalog

Patch reference for the `meta-cmf-bananapi-vcpe` layer: RDK-B EasyMesh
retargeted from BananaPi R4 hardware to x86 LXD containers driving
`mac80211_hwsim` radios. Every patch header carries its own full rationale and
evidence; this file is the index. See `architecture.md` for the system layout,
`steering.md` for the client-steering path, `deploy-and-test.md` for bring-up,
and `wmediumd-multichan.md` for the multi-channel RF layer.

## Categories

- **hwsim** — adaptation to `mac80211_hwsim`, which (on the 6.8 lab) has no
  MLO/802.11be, a single channel context, no MAC ACL capability, no 6 GHz IR, and
  no SAE beacon support. Gated behind the `HWSIM_RADIO` build macro; real R4
  hardware is untouched. **Caveat:** some of these assumptions are 6.8-specific —
  on a 7.0 host loaded `regtest=5`, 6 GHz *is* IR-capable and SAE-H2E works
  (proven, [6ghz.md](6ghz.md) (appendix)),
  so the unconditional 6 GHz-disable / WPA2-forcing patches should become
  capability-gated ([TODO.md](TODO.md) 2–3), not `HWSIM_RADIO`-unconditional.
- **container** — adaptation to the LXD/namespace environment (host-owned
  `/sys`, kernel-global wiphy names/indices, forking-service races).
- **defect** — genuine bugs, real on hardware too, merely exercised here.
  Upstream candidates (see Upstreaming below).
- **build** — compile/portability fixes (32-bit i686 target, `-Werror`, macro
  collisions, cross-compile), no runtime behaviour change.

Patch numbering has gaps (dropped/renumbered during development): rdk-wifi-hal
has no 0016; unified-wifi-mesh has no 0014. Only the files listed below exist.

---

## rdk-wifi-hal (`recipes-ccsp/hal/rdk-wifi-hal/`)

The largest set — the HAL is where hwsim's missing features and the container's
netlink/bridge realities collide. Most steering-path defects (0017-0021) are
universal and upstream-worthy.

| Patch | What & why | Cat |
|---|---|---|
| 0001 define-DEFAULT_MLD_ALLOWED_PHY | Upstream introduced the identifier but never defined it; set the 3-band bitmap (7) so MLO-configured STA builds compile. | build |
| 0002 get_rdk_radio_indices-dont-match-phy_index | In a container the hwsim wiphy keeps its host index (e.g. 40), never 0, so the InterfaceMap `phy_index==0` match fails and init aborts; drop the redundant compare under FEATURE_SINGLE_PHY. | container |
| 0003 set_interface_properties-dont-match-phy_index | Same phy-index mismatch in the second lookup; left `interface_map` empty and crashed downstream. | container |
| 0004 platform_create_vap-guard-NULL-map | Null `map` deref (confirmed core dump) on the MLD path never exercised on real HW; add the argument null-check. | defect |
| 0005 platform_create_vap-guard-NULL-hapd-mld | `for_each_mld_link` derefs `hapd->mld`, never allocated under hwsim though `mld_enable` is set statically; guard like the other call sites. | defect |
| 0006 disable-ieee80211h-under-hwsim | Spectrum-Management IE set unconditionally; exploratory beacon-start probe (a red herring, superseded by 0007). | hwsim |
| 0007 nl80211_put_acl-fix-MAC_ADDRS-attr-type | Disabled-ACL branch sends `NL80211_ATTR_MAC_ADDRS` as a u32 where the kernel expects a nested list; the real cause of `-EOPNOTSUPP` on START_AP. Universal. | defect |
| 0008 skip-acl-under-hwsim | Even a well-formed ACL is rejected because hwsim advertises no MAC-ACL capability; skip `nl80211_put_acl()` for the mesh_backhaul VAPs. | hwsim |
| 0009 backhaul-ssid-passphrase-for-mesh-backhaul-ap | Backhaul AP fell through to the generic serial-derived SSID because the default-getters only checked `mesh_sta`, not `mesh_backhaul`; the backhaul link never associated. Product bug. | defect |
| 0010 dont-register-beacon-frames-on-sta-under-hwsim | Registering BEACON Rx on a STA VAP returns `-EINVAL` under cfg80211/hwsim and stalls the connect loop at auth; skip it. | hwsim |
| 0011 set-sta-operstate-up-so-bridge-forwards | HAL repurposed `.set_operstate`, so a connected STA stays `IF_OPER_DORMANT` and the bridge holds its port non-forwarding; set `IF_OPER_UP`. | defect |
| 0012 dont-notify-supplicant-of-disconnect-when-uninitialized | DISCONNECT forwarded into a never-initialized supplicant context; two SIGSEGVs. Guard on STA state. | defect |
| 0013 dont-take-ovs-path-when-ovs-userspace-is-absent | OVS branch gated on host-visible `/sys/module/openvswitch` (the host's, in a container) and ignored `ovs_add_br()` failure, silently no-oping every enslavement. | container |
| 0014 set-bridge-port-operstate-up-on-enslave | AP-side twin of 0011: hwsim leaves AP ifaces dormant, so EAPOL is dropped at the disabled bridge port and the 4-way handshake stalls. | defect |
| 0015 re-enslave-existing-wds-sta-interface-to-bridge | An already-existing AP_VLAN/WDS iface was re-enabled but never re-added to the bridge after a restart; make membership idempotent. | defect |
| 0017 fix-ap-eapol-rx-when-mlo-configured-but-not-established | AP matched EAPOL against the MLD MAC purely from static config; with MLO configured-but-unestablished every M2 was dropped and no client could associate. Universal. | defect |
| 0018 fix-vap-reconfiguration-stop-ap-and-clamp-mlo-link-id | Restart started an already-running AP and emitted an out-of-range MLO link id, so an EasyMesh-provided SSID never applied. Two defects, must land together. | defect |
| 0019 wifi_hal_send_mgmt_frame-use-the-interface-BSSID | Address 3 was always broadcast; cfg80211 rejects unicast AP action frames with `-EINVAL`. Blocked steering BTM frames. Universal. | defect |
| 0020 wifi_hal_send_mgmt_frame-use-validated-MLO-link-id | Tx path emitted `MLO_LINK_ID=0` for a configured-but-unestablished link; use the validated accessor. | defect |
| 0021 dont-reflect-kernel-del-station-back-as-a-disassociation | DEL_STATION (including hostapd's own stale-entry cleanup on re-auth) was echoed as EVENT_DISASSOC, tearing down the fresh session; steer-back failed on the first attempt every time. Universal. | defect |
| 0022 single-phy-let-START_AP-set-each-radio-channel | Under FEATURE_SINGLE_PHY on 7.0, the standalone `SET_WIPHY`+`WIPHY_FREQ` channel-set is rejected once a sibling AP on the phy beacons (6.8 tolerated it), so only wifi0 came up; skip it and let START_AP carry each VIF's channel. The 6 GHz tri-band F1 fix — see [6ghz.md](6ghz.md). | hwsim |
| 0023 create-wds-sta-on-authorization-not-association | Create the 4-address WDS-STA netdev from the HAL `SET_STATION(authorized)` path, not at association — companion to libhostap 0003/0004, and the reliable trigger since a leftover WDS netdev suppresses `UNEXPECTED_4ADDR`. Fixes the backhaul 4-way (reason-15) — see [6ghz.md](6ghz.md). | defect |

---

## ccsp-one-wifi / OneWifi (`recipes-ccsp/ccsp/ccsp-one-wifi/`)

Build fixes for the EasyMesh build config plus the hwsim radio/security default
overrides (all `HWSIM_RADIO`-gated, layer-local by design).

| Patch | What & why | Cat |
|---|---|---|
| 0001 vap_svc-fix-sign-compare | Signed loop counter vs `num_vaps` under `-Werror=sign-compare` in the BananaPi dml-cache loop. | build |
| 0002 wifi_em-guard-IEEE80211_HDRLEN | `wifi_em.h` redefined the macro that hostap already owns once libhostap became a DEPENDS; `#ifndef` guard. | build |
| 0003 wifi_db-fix-ONEWIFI_DB_SUPPORT-off-branch | The no-DB `#else` branch (only reached with EasyMesh) had a missing forward-decl and a sign-compare; never compiled before. | build |
| 0004 disable-11ax-11be-defaults-under-hwsim | 802.11be/ax + 40 MHz defaults make hwsim beacon-start fail with `-95`; gate them. 6 GHz left off (HE mandatory there). | hwsim |
| 0005 disable-sae-wpa3-defaults-under-hwsim | `NL80211_ATTR_SAE_PWE` makes hwsim reject START_AP (on 6.8); default AP VAPs to WPA2-PSK. **7.0 caveat:** SAE-H2E works on 7.0 hwsim, and 6 GHz *mandates* SAE+PMF — the WPA2 forcing must become band/capability-aware before tri-band. See [TODO.md](TODO.md) 3. | hwsim |
| 0006 disable-6ghz-only-under-hwsim | Every hwsim 6 GHz channel is no-IR under the 6.8-lab regdomain, so 6 GHz can never beacon; disable that radio. **7.0 caveat:** `regtest=5`/`custom_03` makes 6 GHz IR-capable — this should become capability-gated (`HWSIM_6GHZ_CAPABLE`), not unconditional. See [TODO.md](TODO.md) 2. | hwsim |
| 0007 disable-sae-wpa3-sta-defaults-under-hwsim | Completes 0005 for the STA side (`sta_info.security`); without it the backhaul ends mismatched (AP WPA2 vs STA WPA3-SAE) and never authenticates. | hwsim |
| 0008 wifi_db-clamp-channelwidth-20mhz-under-hwsim | Three `HWSIM_RADIO` changes for single-phy tri-band on 7.0: clamp `channelWidth` to 20 MHz (5 GHz 80 / 6 GHz 160 MHz concurrent contexts fail START_AP), set the 6 GHz operating class to 131, and default the country to **GB** (a 6 GHz-IR domain — the F2 regulatory fix; the HAL otherwise falls back to US → 6 GHz no-IR). See [6ghz.md](6ghz.md). | hwsim |
| 0009 easymesh-translator-coherent-cipher-pmf-from-m2 | When applying M2 security the per-radio block set `security.mode` but left `security.encr` stale (GCMP-256), so WPA2+GCMP-256 was invalid and `encode_security_object()` rejected the private subdoc; set a coherent AES/CCMP cipher + PMF-for-WPA3 (also in libwebconfig 0002, the effective build). Fix C — see [6ghz.md](6ghz.md). | defect |

---

## ccsp-one-wifi-libwebconfig (`recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig/`)

| Patch | What & why | Cat |
|---|---|---|
| **0001 easymesh-translator-report-clients-from-full-list** | **Headline fix.** The translator only walked the association *delta* map; on a FULL associate-status refresh (which the co-located agent on the controller hits routinely) that map is empty, so no Client Association Event was emitted and the client never appeared in STAList / the CLI clients-list or topology. Fall back to the full associated-devices map. | defect |
| 0002 easymesh-translator-coherent-cipher-pmf-from-m2 | The **effective** Fix C: `libwifi_webconfig.so` (built by this recipe) is what applies M2 security, so the coherent-cipher/PMF fix must live here — the AP and mesh-STA branches set `security.encr = AES/CCMP` + PMF-required for WPA3. See [6ghz.md](6ghz.md). | defect |

---

## unified-wifi-mesh / EasyMesh (`recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/`)

The EasyMesh controller/agent core. Several standalone defects, the runtime-proven
**client-steering series**, and the DM/startup fixes.

Standalone fixes:

| Patch | What & why | Cat |
|---|---|---|
| 0001 ec_pa_configurator-fix-std-min-type-mismatch | `std::min` fails to deduce on i686 where `size_t` != `unsigned long`; add a cast. | build |
| 0002 securityTypeMap-WPA2-Personal-is-WPA2PSK | "WPA2 Personal" mapped to WSC Enterprise (0x0010) not PSK (0x0020), so the agent reconfigured for SAE and the backhaul suites could not reconcile. | defect |
| 0003 topo-query-do-not-wait-for-disabled-radios | A disabled radio stays `unconfigured` forever, so the agent never sent *any* Topology Response; exclude disabled radios. | defect |
| 0004 crypto-decrypt-final-block-into-callers-buffer | `EVP_DecryptFinal_ex` wrote the last block to discarded scratch while counting its length, so decrypt returned ciphertext bytes as plaintext. Data corruption / security. | defect |
| 0005 fix-heap-overflow-building-btm-request-action-frame | 24-byte heap overflow (buffer sized for payload, written through an `ieee80211_mgmt` overlay) that SIGABRT'd the agent on every client steer. | defect |
| 0011 em_configuration-6ghz-upgrade-guard-match-wpa2psk | Fix B: the 6 GHz WSC-M2 auth-upgrade guard only matched `EM_AUTH_WPA2` (0x10), but "WPA2 Personal" maps to `EM_AUTH_WPA2PSK` (0x20) via 0002, so the 6 GHz M2 wrongly carried WPA2-PSK; match 0x20 too and upgrade the 6 GHz RUID to WPA3/SAE (2.4/5 GHz + backhaul stay WPA2). Shares the `0011` number with the steering ACK patch below. See [6ghz.md](6ghz.md). | defect |

Client-steering series (0007-0016) — landed and proven end-to-end (native
ClientSteer to 1905 to over-air BTM to reassoc to BTM report, repeatable both
ways). See `steering.md`.

| Patch | What & why | Cat |
|---|---|---|
| 0006 tests-honor-caller-supplied-googletest-filter | Built-in negative filter overwrote `--gtest_filter`/`GTEST_FILTER`, so no subset could be run; decide before `InitGoogleTest()`. | build |
| 0007 steering-serialize-request-entirely-from-command-params | Serializer read the source BSSID from data-model slot zero instead of `params->source`, steering from the wrong radio; split into a stateless, testable helper. | defect |
| 0008 tests-add-steering-request-serializer-regression-tests | Seven regression cases against the production serializer (slot-zero sentinel, byte order, request-mode bits). | build |
| 0009 steering-restore-state-after-client-steering | Restore the displaced agent state on ACK/exhaustion/cancel (upstream had no `sta_steer` case — a one-shot bug). | defect |
| 0010 agent-send-BTM-request-on-the-source-VAP | Replaced hardcoded `ap_index 0`/2412 MHz with the real source BSS; fixed request-mode bits, timer byte order, validity interval. | defect |
| 0011 steering-route-1905-ACK-to-the-requesting-radio | Generic 1905 ACK carries no radio identity; correlate by MID so retry cancellation hits the sending radio. | defect |
| 0012 agent-subscribe-all-AP-action-frame-Rx | Agent subscribed only to the first backhaul AP; BTM Responses arrive on the source fronthaul VAP. Subscribe to every AP BSS. | defect |
| 0013 steering-acknowledge-and-complete-BTM-report | The controller's BTM-report ACK was commented out, so agents resent until timeout; send the ACK and complete. | defect |
| 0015 cli-steer-sta-send-the-callers-request | CLI `steer_sta` ignored the caller's params (scraped the whole net dump) and double-freed a subtree; send the real request. | defect |
| 0016 net-node-size-tree-string-buffer | Fixed 16 KB buffer + mis-bounded `strncat`s overflowed the heap on a 3-device `get_sta` tree, aborting steer before send; size to `EM_MAX_EVENT_DATA_LEN`. | defect |

Data-model & startup:

| Patch | What & why | Cat |
|---|---|---|
| 0017 dm-enforce-single-association-invariant | Implement the runtime remove-sta path and enforce non-MLO single association, else a successful steer left two `Associated=1` STAList rows. | defect |
| 0018 al-sap-retry-registration-during-1905-startup | ieee1905's forking service reports started before it accepts connections; the uncaught `ConnectionFailed` SIGABRT'd EasyMesh. Retry for 90 s. | defect |
| 0024 agent-send-sta-topology-notify-synchronously | An association can arrive while the extender is still completing capability/topology synchronization. Accept and send that fire-and-forget STA-list command immediately, then restore the prior radio state; the old queued command expired and the controller never learned the client. | defect |
| 0025 controller-size-sta-frame-body-hex-buffer | A 512-byte association frame requires 1,025 bytes as NUL-terminated hex. The 1,024-byte scratch buffers made `hex()` reject the maximum valid input and passed uninitialized data into SQL. | defect |
| em-cli-live-devices-clients | em_cli web dashboard: build `/api/v1/devices` and `/clients` from the live controller tree instead of hardcoded demo data (controller-only tooling). | — |
| em-cli-live-topology-clients | Make Network Topology consume the same authoritative live client snapshot as `/clients`; the independent topology walk omitted clients from some agents even though `STAList` contained them. | defect |
| em-cli-live-client-bss-classification | Keep a steered client visible when its STA record has no redundant SSID: classify association and fronthaul/backhaul status from the authoritative parent BSS. | defect |

---

## ieee1905-em (`recipes-ccsp/ieee1905/ieee1905-em/`)

| Patch | What & why | Cat |
|---|---|---|
| 0001 rbus-sys-use-TARGET-not-HOST-for-bindgen | `build.rs` passed Cargo `HOST` to bindgen `--target`, producing 64-bit struct layouts in a 32-bit cross build and overflowing a compile-time layout assertion. Use `TARGET`. | build |

---

## rdk-wifi-libhostap (`recipes-ccsp/rdk-wifi-libhostap/rdk-wifi-libhostap/`)

| Patch | What & why | Cat |
|---|---|---|
| 0001 ieee802_11_defs-guard-IEEE80211_HDRLEN | Symmetric `#ifndef` guard for the macro OneWifi's `wifi_em.h` also defines, so whichever header is seen first wins regardless of include order. | build |
| 0002 wpa_sm_notify_disassoc-guard-against-NULL-sm | NULL `sm` deref (breakpad minidump, crash addr 0x44c) during WSC M2 apply; guard like its sibling `wpa_sm_notify_assoc()`. | defect |
| 0003 defer-wds-sta-setup-until-station-authorized | On hwsim, creating the 4-address WDS-STA netdev before the 4-way (at association, and via `ap_sta_set_authorized`) diverts the station's pre-auth EAPOL M4 to the WDS netdev → 4-way times out (reason 15); mark `WLAN_STA_WDS` early but defer creation to `WLAN_STA_AUTHORIZED`. Pairs with rdk-wifi-hal 0023. See [6ghz.md](6ghz.md). | defect |
| 0004 defer-wds-on-rx-from-unknown-until-authorized | Companion to 0003: `ieee802_11_rx_from_unknown` also created the WDS netdev on the first 4-addr frame (M2) before auth; gate that creation on `WLAN_STA_AUTHORIZED` too. | defect |

---

## Non-patch customisation

Not every retarget lives in a `.patch`. The bbappends also ship, outside the
patch stack:

- **steer_drv + steer.sh** — commanded (scripted, non-interactive) steering
  tooling that drives the CLI ClientSteer path. See `steering.md`.
- **em-cli web UI** — the controller-only dashboard (its live-data behaviour is
  the `em-cli-live-devices-clients` patch above).
- **wmediumd/client lifecycle** — `wmediumd-up.sh up` now replaces any daemon
  holding the hwsim registration before starting a refreshed matrix, and treats
  `EBUSY` as fatal. `wlan-client.sh up` refreshes that matrix after adding its
  radio and returns success only after WLAN association plus DHCP. The config
  generator accepts a not-yet-associated client without an empty-key array
  error.
- **em_agent.service `PartOf=onewifi.service`** (unified-wifi-mesh bbappend, extender
  only) — OneWifi holds its VAP config in memory and this image has no WebConfig
  framework to re-push it after an `onewifi` restart, so the fronthaul stayed down;
  coupling the units makes an `onewifi` restart re-drive onboarding → M2 → the config
  push. See [6ghz.md](6ghz.md).

The bbappends further perform `sed` edits to installed scripts, JSON, and
systemd units (DB seeding, service ordering, 1905 socket readiness, MLD config
on a non-MLO target). These expose real product defects but are not in
upstream-ready form — see the assessment below.

---

## Upstreaming

Advisory review only — nothing has been pushed upstream.

**Strong upstream candidates** (platform-independent defects):

- unified-wifi-mesh: **0004** (discarded AES final block), **0005** (heap
  overflow on every steer), **0002** (WPA2-Personal encoded as Enterprise),
  **0003** (disabled radio blocks all topology responses), **0001** (32-bit
  build). The steering series **0006-0013** and DM/startup **0016-0018** are
  submittable with their new focused tests.
- rdk-wifi-hal: **0007** (ACL attribute type), **0009** (backhaul credentials),
  **0012** (uninitialized-disconnect guard), **0017** (MLO-unestablished EAPOL),
  **0004/0005** (null guards), **0015** (WDS re-enslave), **0019/0021**
  (mgmt-frame BSSID, DEL_STATION echo). All universal.
- ieee1905-em **0001** (Cargo HOST vs TARGET), OneWifi **0003** (no-DB branch),
  rdk-wifi-libhostap **0002** (NULL sm guard).

**Keep layer-local** (hwsim/container policy, not mainline):

- All `HWSIM_RADIO`-gated defaults: OneWifi 0004-0007, rdk-wifi-hal 0006/0008/0010.
- Patches that encode this topology via compile flags (rdk-wifi-hal
  0002/0003 phy-index, 0011/0014 operstate, 0013 OVS) need generalizing to
  runtime capability/ambiguity checks before submission, not a build gate.
- Superseded on current upstream: rdk-wifi-hal 0001, OneWifi 0001/0002,
  libhostap 0001.

**Submission-quality gate:** rebase onto the target branch, reduce to one root
cause, strip lab identifiers (host names, LXD names, fixed MACs, passwords,
paths), add a deterministic test at each seam, state whether the bug is
universal/platform/simulation-only, and keep the layer patch until the upstream
commit lands in the recipe SRCREV.
