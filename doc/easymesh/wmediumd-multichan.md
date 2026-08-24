# Multichannel wmediumd

The default lab runs **bare** `mac80211_hwsim`: frames are delivered at a flat
signal, so there is no RSSI gradient for policy-driven roaming/coverage to act on
(commanded steering still works — see [steering.md](steering/steering.md)). wmediumd adds a
real per-link RF model. Running it while the pool is loaded `channels=2` (one phy
carrying concurrent 2.4 + 5 GHz, `FEATURE_SINGLE_PHY`) needs the pieces below.

> **Runnable tooling + operator bring-up live in this layer's `gen/`**:
> `gen/hwsim/` (kernel-module patch + build), `gen/wmediumd/` (patched daemon,
> `gen-config.sh`, `wmediumd-up.sh`), and `docs/wmediumd-multichan.md`. This file
> is the design/state record.

## Two required pieces

1. **Kernel (hwsim):** stock `mac80211_hwsim` refuses `HWSIM_CMD_REGISTER` at
   `channels > 1` (`-EOPNOTSUPP`). The guard is precautionary — the kernel↔
   wmediumd protocol already carries `HWSIM_ATTR_FREQ`, and 6.8.0-136's cloned-RX
   path is already chanctx-aware. A one-line patch downgrades the guard to a
   warning (`gen/hwsim/patches/0001`). Loading the stock module at
   `channels=2` for *bare* hwsim needs no patch — only wmediumd registration does.
2. **wmediumd:** channel-aware (WMD 1–4) plus the correct radio identity in its
   config (the `42:` fix below).

## Root cause that blocked FEATURE_SINGLE_PHY (config, not code)

wmediumd keys a radio by the frame's `HWSIM_ATTR_ADDR_TRANSMITTER`, which hwsim
derives as `perm_addr | 0x40` on byte 0 — the `42:…` hw/TX address, **not** the
`02:…` perm address in `/sys/class/ieee80211/*/macaddress`. A config listing
`02:` ids makes every by-addr lookup miss (`Unable to find sender station …`),
which at FEATURE_SINGLE_PHY (many BSSIDs per radio) drops nearly all frames → zero
associations. The generator must emit the `42:` id. This — not WMD1/WMD2 — was
the association blocker.

## Design — frequency belongs to the VIF, not the phy

A single-phy AP owns multiple VIFs on different channels, so per-radio frequency
is wrong; so is attaching frequency to the `addrs[]` RX-filter
(`HWSIM_CMD_ADD_MAC_ADDR` is *reception eligibility*, not ownership — a client MAC
legitimately appears under its own radio and every AP it joined). **VIF ownership
is learned from transmitted frames:** each TX frame carries the 802.11 TA (the
VIF) and the owning radio's hw address. A global `mc_vif_state {vif → owner,
freq}` table records it; destination-frequency lookups consult owned VIFs only.

## Patch series (WMD 1–4)

- **WMD 1** — owned-VIF active frequency, learned from TX (`TA`,
  `HWSIM_ATTR_FREQ`, `HWSIM_ATTR_ADDR_TRANSMITTER`). (Also fixed an
  `ADD/DEL_MAC_ADDR` heap overflow that assumed a 6-byte `struct addr`.)
- **WMD 2** — channel-aware ACK: `ELIGIBLE / OFFCHANNEL / FREQ_UNKNOWN`;
  off-channel forces NO-ACK and no delivery (off-channel ghost-ACK suppression).
- **WMD 3** — frequency-scoped interference: `(src,dst)` bucket keyed by
  frequency; the victim calc consumes only the matching-frequency bucket.
- **WMD 4** — `wmediumd -T` self-test + counters (freq-scoping + the WMD1
  ownership invariant, no hostapd/netlink).
- **Deferred:** replace the one-line kernel guard with a capability handshake
  (`HWSIM_ATTR_WMEDIUMD_CAPS`) so old wmediumd stays rejected at `channels=2`.

## Acceptance ladder

```text
1  channels=2 registration                        PASS
2  AP/STA on 2437 through wmediumd                 PASS
3  AP/STA on 5180 through wmediumd                 PASS
4  both bands simultaneously                       PASS
5  off-channel stale destination gets NO ACK       PASS   (ghost fix)
6  interference accounting frequency-isolated       PASS   (wmediumd -T)
7  one phy, 2437 + 5180 concurrently                PASS   (FEATURE_SINGLE_PHY)
8a multichannel wmediumd across netns              PASS
8b LXD multi-BSSID deploy (3 radios / 33 VAPs)     PASS   (Unable-to-find-sender = 0)
9  EasyMesh onboarding/roam integration            EasyMesh work, not wmediumd
```

Items 1–8b are frozen; no wmediumd redesign is indicated by the remaining
EasyMesh onboarding issues (see [architecture.md](architecture.md) "current
state").

## Verify a bring-up (don't trust "it registered")

1. `dmesg | grep hwsim` shows the `EXPERIMENTAL wmediumd with 2 channels` warning
   (patched module loaded).
2. the wmediumd log has **zero** `Unable to find sender` (ids are `42:`).
3. from a client, `iw dev wlan0 scan` signal is no longer flat −27 dBm.
4. `wmediumd -T` passes.

## 6 GHz — platform-dependent

hwsim models 6 GHz; whether an **AP** can beacon depends on the applied regdomain,
which in practice tracks the kernel generation:

- **6.8.0-136 (default lab):** the applied regdom leaves 6 GHz `NO_IR`; a 6 GHz AP
  needs a power-mode designation (`IEEE80211_CHAN_ALLOW_6GHZ_VLP_AP`, absent here)
  or `REGULATORY_WIPHY_SELF_MANAGED`. A plain non-NO_IR reg rule is insufficient
  on this kernel, so 6 GHz stays deferred. `channels=3` tri-band concurrency
  itself works.
- **7.0:** loading with `regtest=5` selects `custom_03`, under which 6 GHz is
  **IR-capable (0 NO_IR)** and a 6 GHz AP beacons on 5975 with **no** kernel patch
  — proven standalone (SAE-H2E + PMF + 4-way). The VLP-AP flag is available but not
  required there. See
  [6ghz.md](6ghz.md) (appendix).
  Running 5975 through **multichannel wmediumd** at `channels=3` (wifi0@2437 +
  wifi1@5180 + wifi2@5975) is the next integration step; the WMD1–4 model is
  frequency-scoped and already handles the third context.
