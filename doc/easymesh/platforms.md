# Platforms — dual-band (6.8) vs tri-band (7.0)

The same EasyMesh lab (`bpibroadband` controller, `bpiap` extender(s), `wlan-client`
station(s)) runs on two run targets. They share the source tree and the deploy
tooling; they differ in **three** things only: the kernel, the hwsim pool, and one
image build flag. This doc is the deployment-requirements matrix — read it with
[deploy-and-test.md](deploy-and-test.md) (the step-by-step procedure) and
[6ghz.md](6ghz.md) (the 6 GHz story and the 6.8-vs-7.0 kernel background).

## At a glance

| | **rev150 — dual band** | **rev120 — tri band** |
|---|---|---|
| Kernel | `6.8.0-136-generic` | `7.0.0-28-generic` |
| Bands | 2.4 + 5 GHz (wifi0 + wifi1) | 2.4 + 5 + 6 GHz (wifi0 + wifi1 + wifi2) |
| **Image flag** `HWSIM_6GHZ_CAPABLE` | **unset / `0`** | **`"1"`** |
| wifi2 (6 GHz) | present but **down** (disabled) | **up** @ ch227 / 6135 MHz |
| Security | WPA2-PSK all bands | WPA2 backhaul + 2.4/5; **WPA3-SAE + PMF on 6 GHz** |
| hwsim module patch | `0001` (multichannel) | `0001` (multichannel) |
| hwsim load | `radios=24 channels=2` (`regtest=0`) | `radios=24 channels=3 regtest=5` |
| 6 GHz regdomain | n/a (dual) | `custom_03` via `regtest=5` (6 GHz IR-capable) |
| Reference build | tree `…-0812`, image `X86EMLTR…_2026081300…` | tree `…-0814`, image `X86EMLTR…_2026081416…` |
| wmediumd | off (flat medium) | off (flat medium) |

Everything else — the layer, the recipe patches, the containers, `bpi.sh` /
`wlan-client.sh` — is identical.

## Support scope

**Linux 7.0 is the supported tri-band platform and the primary lab for
steering-policy work. Linux 6.8 is supported only for the dual-band baseline; its
tri-band path is unvalidated and outside current project scope.**

| Target | Role | Status |
|---|---|---|
| rev120 · `7.0.0-28` · channels=3 | Primary tri-band steering lab | **Supported — frozen** |
| rev150 · `6.8.0-136` · channels=2 | Dual-band regression / reference | Supported |
| Linux 6.8 · channels=3 · patched 6 GHz | Research experiment only | **Not supported / not pursued** |

**Why not chase 6.8 tri-band.** The goal is steering-policy experimentation, not
coercing an older kernel into 6 GHz. 7.0 already gives the complete, validated
foundation — concurrent 2.4/5/6 GHz on one phy, IR-capable 6 GHz via
`regtest=5`/`custom_03`, SAE-H2E + mandatory PMF, EasyMesh onboarding + per-radio
WSC M2, and extender 6 GHz fronthaul + client association. A 6.8 tri-band path would
add a custom strict-regd hwsim patch, unresolved START_AP/SAE behaviour, older 6 GHz
regulatory semantics, and another kernel/image/module combination — which weakens
experiment attribution (a failure could be mistaken for a wmediumd or steering-policy
defect). That is the opposite of what this lab needs.

### Frozen — pin every axis

"Frozen" means every experiment artifact **pins** the exact versions it ran against,
and the platform does **not** auto-follow newer kernels while steering baselines are
being established. Pin all of:

| Axis | Frozen value (7.0 primary — 2026-08-14) |
|---|---|
| Kernel | `7.0.0-28-generic` (Ubuntu 24.04, `linux-hwe-7.0`) |
| hwsim module | stock 7.0 source + `gen/hwsim/patches/0001` (sha256 `c7f2f17d…`); loaded `radios=24 channels=3 regtest=5` (running srcversion `5C673B9A…`) |
| Regdomain | `custom_03` (via `regtest=5`) → 6 GHz IR-capable; effective country GB (DFS-ETSI) |
| Image build | 0814 tree, `HWSIM_6GHZ_CAPABLE=1`; `X86EMLTRBPIBB_…164047` + `X86EMLTRBPIAP_…164733` |
| wmediumd | to pin once proven with channels=3 — see [wmediumd-multichan.md](wmediumd-multichan.md) |
| Config | one hwsim phy per container (`FEATURE_SINGLE_PHY`); `channels=3` |

Record these (or the current equivalents) in each experiment's run record, and do not
bump the kernel/module/image out from under an in-progress steering baseline.

## Do we need separate images? **Yes — one build flag**

The only source difference is `HWSIM_6GHZ_CAPABLE` in each build dir's
`conf/local.conf`. You build **from the same tree, twice**:

- **unset / `"0"` → dual-band image.** `ccsp-one-wifi` 0006 disables the 6 GHz radio
  and 0005/0007 force WPA2 (both gated `HWSIM_RADIO && !HWSIM_6GHZ_CAPABLE`). wifi2 is
  down, all bands WPA2. Runs on **6.8** (and on 7.0 as dual). This is what rev150 runs.
- **`"1"` → tri-band image.** wifi2 is enabled and the WPA3/SAE + MFP-required defaults
  are restored so the controller's 6 GHz WSC-M2 can carry SAE-H2E. **7.0 only.** This is
  what rev120 runs.

**Why the tri-band (`=1`) image is 7.0-only:** it restores WPA3/SAE for the 6 GHz VAP,
but 6.8's `mac80211_hwsim` rejects SAE (`NL80211_ATTR_SAE_PWE` → `-EOPNOTSUPP`) and its
regdomain leaves 6 GHz NO_IR, so wifi2 can never beacon there. 7.0's `custom_03`
(selected by `regtest=5`) makes 6 GHz IR-capable and its hwsim accepts SAE-H2E — see
[6ghz.md](6ghz.md). So the flag must **match the target**: `0` for 6.8/dual, `1` for
7.0/tri. The controller and the extender image each need the matching flag.

> To flip: edit `HWSIM_6GHZ_CAPABLE` in `build-qemux86bpibroadband/conf/local.conf` and
> `build-qemux86bpiap/conf/local.conf`, then rebuild both images. No separate tree
> needed — the `…-0812` (dual) and `…-0814` (tri) trees differ only by this flag.

## Kernel + hwsim module (per target)

Both targets need the **multichannel** hwsim patch
(`gen/hwsim/patches/0001-…-allow-multichannel-wmediumd.patch`) so one phy can hold more
than one channel context (`FEATURE_SINGLE_PHY` gives each container exactly one phy).
`gen/hwsim/build-hwsim.sh` is kernel-generation aware — run it **on the run host** to
build+install the patched module and load the pool:

- **rev150 (6.8, dual):**
  ```sh
  cd gen/hwsim && ./build-hwsim.sh --load       # patched module + modprobe radios=24 channels=2
  ```
- **rev120 (7.0, tri):**
  ```sh
  cd gen/hwsim && ./build-hwsim.sh --6ghz --load # patched module + modprobe radios=24 channels=3 regtest=5
  ```

`regtest=5` (→ `custom_03`) is what makes 6 GHz IR-capable on 7.0; **don't** rely on
`bpi.sh`'s auto-load for the tri-band pool — it loads `channels=${HWSIM_CHANNELS:-2}`
with **no** `regtest`, so pre-load with `build-hwsim.sh --6ghz --load` first.

The 6.8 6 GHz strict-regd patch (`0002`) is **prior-work research** for a 6.8
tri-band path that is **not supported or pursued** (see *Support scope*); it stays in
the repo as reference only. Neither supported target applies it (rev150 is dual,
rev120 is 7.0).

## Deploy (per target)

The procedure is the same on both — only the image and the pool differ. Full steps and
bridges are in [deploy-and-test.md](deploy-and-test.md); the target-specific bits:

**rev150 — dual band (6.8)**
1. Build the **`HWSIM_6GHZ_CAPABLE=0`** images on the build host.
2. On rev150: `cd gen/hwsim && ./build-hwsim.sh --load` (channels=2).
3. `cd gen && HWSIM_CHANNELS=2 ./bpi.sh <BPIBB> -b <wan-br> -l <lan-br> -F` (controller),
   then `HWSIM_CHANNELS=2 ./bpi.sh <BPIAP> -F` (and `-i 1 -F`, `-i 2 -F` for more
   extenders), then `wlan-client.sh …` for stations.

**rev120 — tri band (7.0)**
1. Build the **`HWSIM_6GHZ_CAPABLE=1`** images on the build host.
2. On rev120: `cd gen/hwsim && ./build-hwsim.sh --6ghz --load` (channels=3, regtest=5).
3. `cd gen && HWSIM_CHANNELS=3 ./bpi.sh <BPIBB> -b <wan-br> -l <lan-br> -F` (controller),
   then `HWSIM_CHANNELS=3 ./bpi.sh <BPIAP> -F`, then `wlan-client.sh …`.

## Verify

Expected extender band state (from `iw dev wifiN info` inside `bpiap`):

```
rev150 (dual):  wifi0 up ch6(2.4)   wifi1 up ch36(5)    wifi2 DOWN
rev120 (tri):   wifi0 up ch6(2.4)   wifi1 up ch36(5)    wifi2 UP ch227(6135, 6 GHz)
```

For tri, the 6 GHz security acceptance is a client SAE-H2E association to `wifi2`
(`key_mgmt=SAE`, `pmf=2`, `BIP`) — see [6ghz.md](6ghz.md).

## Optional — wmediumd RF gradient

Both labs run on the **flat** hwsim medium by default (every radio hears every other
at full strength), which is enough to form the mesh and steer clients by command. For
per-link RF control (path loss, asymmetric links, roaming scenarios) load wmediumd on
top — see [wmediumd-multichan.md](wmediumd-multichan.md) and, for scripted RF
scenarios, [steering/wmediumd-configurator.md](steering/wmediumd-configurator.md).
