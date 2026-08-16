# Client steering

Directed (commanded) 802.11v client steering: the controller tells a source
agent to move a client to a target BSS. See [architecture.md](../architecture.md)
for the surrounding stack and [deploy-and-test.md](../deploy-and-test.md) for lab
bring-up.

## The flow

A controller database update alone is **not** a steer — there is a control-plane
request and an over-the-air action.

```text
EasyMesh controller     source agent / OneWifi      client STA        target AP
      | ClientSteer (TR-181)   |                        |                  |
      |─ 1905 Client Steering ─▶|                        |                  |
      |    Request CMDU         |─ RBus RawFrame Tx ──────▶ 802.11v BTM Req  |
      |                         |                        |  evaluate target |
      |                         |◀─ 802.11v BTM Response ─|                  |
      |                         |                        |── reassociate ───▶|
      |                         |                        |◀── 4-way HS ──────|
      |◀──── BTM Report / topology + client association update ─────────────|
```

- Controller: a `ClientSteer` payload (shaped as the data model:
  `Network → DeviceList[source AL-MAC] → RadioList[source RUID] →
  BSSList[source BSSID] → STAList[STA] → ClientSteer{TargetBSSID, RequestMode,
  timers}`) drives `em_ctrl`, which emits a **1905 Client Steering Request** to
  the source agent (`send_client_steering_req_msg … Send Successful`).
- Source agent: converts it to an over-air **802.11v BTM Request** (via the
  OneWifi RBus RawFrame action API) to the STA.
- STA: replies with a **BTM Report**; on accept it reassociates to the target and
  the controller model converges. Report **status 0 = accept** (roamed);
  **status 7 = "no suitable candidate"** (rejected — see gotchas).

## Tooling (shipped in the controller image)

`onewifi_em_cli` (the web UI) exposes no steer route, so two small tools ship in
the controller image (built by the `unified-wifi-mesh` recipe):

- **`steer_drv "steer_sta OneWifiMesh" <payload.json>`** — the low-level driver.
  Links `libemcli.so`: `set_remote_addr(127.0.0.1,49153)` →
  `get_network_tree_by_file(json)` → `exec("steer_sta OneWifiMesh", node)`.
- **`steer.sh <STA_MAC> <TARGET_BSSID> [op_class] [channel]`** — the ergonomic
  wrapper. Resolves the source device (AL-MAC/RUID/source BSSID) for the STA from
  the `OneWifiMesh` DB, derives op-class/channel defaults from the target's band,
  builds the `ClientSteer` payload, and calls `steer_drv`.

```sh
# steer STA 02:00:00:00:03:00 to a target 5 GHz fronthaul BSS on Extender-2
lxc exec bpibroadband -- /usr/bin/steer.sh 02:00:00:00:03:00 02:00:00:51:38:4f
```

`steer.sh` refuses when the model already places the STA on the target
(source == target — a stale/lost-report artifact); resync first.

## Acceptance test

A steer passed when all of these hold:

```text
controller log  Client Steering Request (N) Send Successful
agent log       BTM request for <STA>  (RawFrame Tx)
controller log  Client BTM Report for sta <STA>, status 0
client          iw dev wlan0 link  →  TARGET BSSID  (roamed, ~3 s)
controller DB   STAList <STA> BSSID = TARGET
```

Proven repeatably (both directions, ~3 s each) on the fresh single-phy lab:
`steer.sh` moved a client Extender-1 → Extender-2 and back, each with BTM Report
status 0.

Preconditions: the controller `STAList` row for the STA must match the **source**
BSSID (the model must reflect where the client actually is — resync if it lags),
and the target must be a `private_ssid` BSS the client can see
(`iw dev wlan0 scan`).

## Gotchas

- **Unpinned supplicant.** The client's `wpa_supplicant` must have **no** `bssid=`
  pin for the network — a pin makes the steer target an *illegal candidate* and
  the STA rejects with **BTM status 7**. `wlan-client.sh` clients are unpinned by
  default; only manual restarts with a pinned `wpa.conf` cause this.
- **Model lag.** BTM-report loss / the stale-assoc race can leave `STAList`
  showing the client on a node it already left. `steer.sh` reads the source from
  the model, so a stale model produces a wrong or no-op steer — resync (a clean
  reassociation) before steering.
- **Flat RSSI vs policy steering.** *Commanded* steering (`Steering_Mandate` +
  disassoc-imminent) needs no RF gradient and works on bare hwsim. *Autonomous /
  policy* steering (the controller deciding on its own from RSSI) needs a real
  gradient — that is what wmediumd provides
  ([wmediumd-multichan.md](../wmediumd-multichan.md)); without it every AP looks
  equally strong and there is nothing to decide on.
