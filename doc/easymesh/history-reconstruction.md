# 0815 to 0824 history reconstruction map

This file records how the 191 EasyMesh-era commits on
`codex/0815-clean` at `9703300` were represented by the 27 functional
commits on `codex/0824-clean` before this audit document was added.

The reconstruction starts from the common pre-EasyMesh parent `6d87e235`.
Its functional checkpoint has tree
`207ab4be6f16225ca43ee79f354e0df07e44738c`, exactly matching
`9703300^{tree}`. A row can identify more than one reconstructed commit when
the original change crossed product, test, documentation, or infrastructure
boundaries. Mapping means that the final accepted effect is owned by the named
new commit; intermediate approaches that were later superseded were not
reintroduced.

| Original | Reconstructed owner(s) | Original subject |
| --- | --- | --- |
| `24a95d9` | `a96afee` | platform: establish x86 EasyMesh container targets |
| `112a73f` | `1332e55` | wifi: adapt HAL and hostap for single-phy hwsim |
| `6fe294f` | `ba9c745` | onewifi: support hwsim configuration and reliable STA export |
| `dd0a091` | `3cc3ca7` | easymesh: repair onboarding topology and steering flows |
| `bc6a98a` | `2130b63` | lab: add reproducible hwsim wmediumd and deployment tooling |
| `a9441a2` | `e55f1ac` | docs: describe and operate the EasyMesh evaluation lab |
| `d4dca04` | `9ede605` | easymesh: replace forced topology recovery with orchestration fix |
| `156d684` | `c67c804` | docs: define the 0815 patch boundaries and acceptance gates |
| `56cf4a4` | `670e401` | lab: make deployment locking user-neutral |
| `ae65be4` | `670e401`, `aaa4d00` | wmediumd: keep shared runtime state outside sticky tmp |
| `95d4990` | `aaa4d00` | wmediumd: replace daemon across tooling checkouts |
| `d22b076` | `670e401` | lab: gate station creation on EasyMesh export |
| `73e7c1e` | `670e401` | lab: allow full station model convergence interval |
| `83b998a` | `670e401`, `c67c804`, `ec4e797` | docs: consolidate 0815 lab guidance and access procedures |
| `1dd68a3` | `aaa4d00` | wmediumd: replace legacy lab daemon without control socket |
| `d4ba83c` | `f7a1a0d` | tests: make parity steering and health checks portable |
| `6ad6b61` | `c67c804` | docs: consolidate runtime parity, diagnostics, and optimizer architecture |
| `90ca50f` | `c67c804` | docs: publish readable optimizer architecture PDF |
| `c380e04` | `9ede605` | easymesh: size AP metrics response for scale |
| `bf6867a` | `670e401` | lab: leave client cold-boot order to runtime |
| `7d373c4` | `c67c804` | docs: record scale-safe reboot acceptance |
| `6a4dfd0` | `61ad083`, `c67c804` | webui: implement topology layout and export |
| `e9ad496` | `61ad083` | webui: make topology layout refresh-safe |
| `313dd47` | `c67c804` | docs: add rev130 reboot recovery procedure |
| `1ad8308` | `61ad083`, `c67c804`, `ec4e797`, `f7a1a0d` | easymesh: harden topology ownership and recovery |
| `beef631` | `61ad083`, `c67c804` | webui: serve live device and client inventory |
| `34c08d6` | `47b57f1`, `c67c804` | vm: build reproducible Boardfarm EasyMesh appliance |
| `23e52a7` | `47b57f1`, `c67c804` | vm: add thin and precooked lab workflows |
| `0d636f0` | `47b57f1` | docs: document supported VM host setup and thin box import |
| `ed092ad` | `47b57f1` | vm: package and validate Dropbox thin-lab handoff |
| `b939a03` | `61ad083`, `c67c804`, `ec4e797`, `f7a1a0d` | easymesh: test RF outage with live topology refresh |
| `8a39244` | `61ad083` | webui: improve topology interaction and labels |
| `0d3b7b7` | `c67c804`, `f7a1a0d` | tests: add live client carousel scenario |
| `074fd16` | `c67c804` | docs: explain wmediumd operation and controls |
| `4e550a5` | `47b57f1`, `8823db9`, `c67c804`, `e7062d4`, `ec4e797` | easymesh: enable live metrics and RCPI monitoring |
| `d5fd725` | `ec4e797` | configurator: accept null topology collections |
| `5f8cd4b` | `c67c804` | docs: add EasyMesh packet capture workflow |
| `4bcddd6` | `47b57f1` | vm: refresh thin runtime revision |
| `cb1e791` | `47b57f1` | vm: reconcile thin and offline runtime inputs |
| `dd6f4ba` | `47b57f1` | vm: propagate the selected EasyMesh revision |
| `3293af8` | `47b57f1` | vm: make thin Boardfarm setup resumable |
| `7235252` | `8823db9`, `c67c804` | easymesh: keep topology client ownership authoritative |
| `cd72102` | `f7a1a0d` | tests: make RF recovery scenarios deterministic |
| `c2e8ce7` | `47b57f1` | vm: add packaged lab operator guide |
| `1b5d546` | `47b57f1` | vm: advance accepted 0818 runtime pin |
| `a27c39e` | `47b57f1`, `c67c804`, `f7a1a0d` | tests: phase carousel placement transitions |
| `2e4d019` | `c67c804` | docs: define steering policy research roadmap |
| `fc5e72b` | `c67c804` | docs: add EasyMesh lab presentation |
| `63af221` | `c67c804` | docs: index 0818 research deliverables |
| `8d5400b` | `f7a1a0d` | tests: preserve carousel association failure evidence |
| `ca17171` | `8823db9` | easymesh: preserve AL-SAP stream message boundaries |
| `ec8b423` | `47b57f1`, `f7a1a0d` | tests: restore steering medium on every exit |
| `fd80bcf` | `c67c804` | docs: record AL-SAP framing acceptance |
| `73d1821` | `47b57f1`, `f7a1a0d` | tests: retry transient LXC link observations |
| `c57d8b2` | `1e68c34` | wmediumd: classify transient clone delivery rejection |
| `bc9258d` | `c67c804` | docs: close wmediumd command-2 diagnostic debt |
| `378e43f` | `47b57f1`, `f7a1a0d` | tests: journal steering transaction completion |
| `e01e6f3` | `c67c804` | docs: record commanded steering soak acceptance |
| `983640c` | `c67c804` | docs: localize extender liveness gap |
| `d117613` | `073a1d4` | ieee1905: notify expired topology neighbors |
| `3590c06` | `c67c804` | docs: record ieee1905 neighbor expiry publication |
| `22adff8` | `8823db9`, `f7a1a0d` | easymesh: route controller logs through journald |
| `911063f` | `c67c804` | docs: record bounded controller logging |
| `8c5176b` | `073a1d4`, `8823db9`, `e7062d4`, `f7a1a0d` | easymesh: close P0 topology and service-state gaps |
| `a86d0f8` | `47b57f1`, `f7a1a0d` | tests: add P0 reconstruction and memory gates |
| `93f34dc` | `47b57f1`, `670e401`, `c67c804` | docs: reconcile EasyMesh guidance with P0 state |
| `218528d` | `47b57f1`, `c67c804` | vm: parameterize wmediumd deployment provenance |
| `9a9bd45` | `47b57f1`, `9228203`, `f7a1a0d` | wifi: serialize log4c category creation |
| `0bd827d` | `670e401`, `c67c804`, `f7a1a0d` | steering: add name-aware command adapter |
| `e01c5ca` | `47b57f1` | vm: pin current thin runtime artifacts |
| `7536d8c` | `8823db9` | easymesh: service radio timers under frame load |
| `966c4e3` | `47b57f1` | vm: preserve Vagrant shares during bootstrap |
| `5156c2d` | `c67c804` | docs: add accepted EasyMesh demo runbook |
| `798ad21` | `9228203`, `f7a1a0d` | selfheal: prevent cross-user SNMP process multiplication |
| `0c96173` | `c67c804` | docs: record SNMP self-heal process multiplication |
| `38294e1` | `3e545d7`, `f7a1a0d` | webui: preserve optimized topology across refresh |
| `9b225df` | `f7a1a0d` | tests: support build-host Node for topology regression |
| `6f587ed` | `3e545d7`, `f7a1a0d` | webui: refresh persistent assets on image update |
| `15c3088` | `670e401`, `f7a1a0d` | gen: reserve stopped-container hwsim radios |
| `1cbd859` | `3e545d7`, `f7a1a0d` | webui: isolate topology layout render state |
| `0e9dfec` | `f7a1a0d` | tests: audit active hwsim profile assignments |
| `a50a008` | `e7062d4` | onewifi: resolve duplicate extender AL MAC |
| `3c8a41f` | `3e545d7`, `f7a1a0d` | webui: optimize rendered topology nodes |
| `b9be9f5` | `f7a1a0d` | tests: exercise topology optimizer render nodes |
| `e00629e` | `c67c804` | docs: record current rev130 lab acceptance |
| `cf2aa76` | `3e545d7` | metrics: repair defaults for reloaded radios |
| `b8437ac` | `3e545d7`, `f7a1a0d` | webui: enable metrics across the live mesh |
| `21401c7` | `47b57f1` | vm: require client metrics during cold start |
| `e28f562` | `3e545d7` | metrics: preserve agent profile during onboarding |
| `50c955f` | `11426aa` | diagnostics: install instant PSS analysis tools |
| `7babba3` | `11426aa` | diagnostics: retain supplied script names |
| `9206e02` | `3e545d7` | metrics: persist topology response profile |
| `39d2b92` | `3e545d7`, `47b57f1`, `e7062d4` | metrics: complete mesh-wide reporting and uptime |
| `16b5bcf` | `c67c804` | docs: close functional P0 acceptance |
| `10b2bec` | `a181543`, `c67c804` | optimizer: establish external observation and replay core |
| `21eab6f` | `a181543` | tests: exercise optimizer through crossover replay |
| `35ba466` | `c67c804`, `ec4e797` | configurator: generate deterministic RF world corpus |
| `466f284` | `a181543`, `c67c804` | optimizer: define capability-gated scenario matrix |
| `9a1c159` | `1e68c34`, `c67c804`, `ec4e797` | wmediumd: control SNR by frame frequency |
| `3d71621` | `a181543`, `c67c804` | optimizer: admit frequency-aware small profile |
| `4b7b577` | `a181543`, `c67c804` | optimizer: add explicit band-upgrade baseline |
| `d89c4ce` | `3e545d7`, `a181543`, `c67c804` | optimizer: expose controller BSS inventory |
| `a53ec8e` | `a181543`, `c67c804` | optimizer: back off ignored steering attempts |
| `7dc91df` | `a181543`, `c67c804` | optimizer: simulate golden worlds in closed loop |
| `fd21cd7` | `a181543`, `c67c804` | optimizer: plan backhaul trees and channel widths |
| `be0e216` | `a181543`, `c67c804` | optimizer: bound preassociation band preference |
| `8dfb892` | `c67c804` | docs: record candidate metrics implementation boundary |
| `c28d801` | `1e68c34`, `670e401`, `aaa4d00`, `ec4e797` | wmediumd: add read-only metrics control plane |
| `a79ca4f` | `1ad0a7f`, `736db17` | easymesh: complete candidate-link RCPI transaction |
| `2d00849` | `1ad0a7f` | build: apply candidate RCPI patch from HAL source root |
| `71e95a4` | `736db17` | easymesh: fix candidate metrics identifier type |
| `292aa69` | `f7a1a0d` | tests: gate candidate RCPI in long soak |
| `d71bb96` | `c67c804` | docs: define long-duration soak acceptance |
| `73aa31e` | `736db17` | easymesh: refresh candidate metrics CLI artifact |
| `b614aaf` | `736db17`, `e7062d4` | easymesh: accept asynchronous candidate metrics result |
| `3088c25` | `ec4e797` | configurator: ignore stopped lab containers |
| `7bb9c7e` | `e7062d4` | onewifi: patch the runtime candidate metrics encoder |
| `5bebe86` | `670e401` | lxd: hot-attach candidate metrics after run mount |
| `3b12399` | `736db17` | easymesh: deliver correlated candidate metrics response |
| `e72859f` | `a181543` | optimizer: consume live candidate metrics |
| `239d31f` | `736db17` | metrics: expose associated report receipt time |
| `4048f94` | `ec4e797` | configurator: validate complete frozen lab scale |
| `b89d686` | `a181543` | optimizer: trust live metric receipt time |
| `5548982` | `a181543` | optimizer: query candidate metrics per radio |
| `33e09a0` | `736db17` | easymesh: renew WSC enrollee state on retry |
| `290d53f` | `a181543` | optimizer: bound unassociated metrics to same band |
| `0b30d16` | `736db17` | metrics: retain candidates on correlated radio |
| `bb342ad` | `736db17`, `c67c804` | webui: restore topology band metadata |
| `65387bd` | `1ad0a7f`, `670e401` | hwsim: preserve candidate metrics across restarts |
| `bb27382` | `670e401`, `736db17` | easymesh: complete live candidate observations |
| `a38df5e` | `a181543`, `ec4e797`, `f7a1a0d` | optimizer: enforce complete policy-ready snapshots |
| `6336f3d` | `47b57f1` | vm: converge metrics policy from observed reports |
| `ac4fa74` | `670e401`, `c67c804` | docs: publish optimizer manual and active soak state |
| `5374527` | `f7a1a0d` | tests: separate soak recovery and process gates |
| `ec5543f` | `f7a1a0d` | tests: retry read-only LXC soak probes |
| `3915654` | `ec4e797` | configurator: tolerate transient inventory transport loss |
| `60044ba` | `f7a1a0d` | tests: harden candidate identity probes |
| `82a642a` | `f7a1a0d` | tests: distinguish LXC transport from traffic failure |
| `22897a9` | `f7a1a0d` | tests: serialize soak traffic probes |
| `9499b01` | `f7a1a0d` | tests: recognize LXD signal exit status |
| `74b0d95` | `c67c804` | docs: record corrected final soak campaign |
| `2a15c95` | `f7a1a0d` | tests: retry idempotent carousel link restore |
| `8b6e3f1` | `c67c804` | docs: supersede interrupted soak campaign |
| `8395b9a` | `3671cef` | easymesh: reconcile silent roam ownership by age |
| `fa15b1a` | `3671cef` | easymesh: fix association-age build type |
| `159e206` | `3671cef` | easymesh: keep association-age evidence current |
| `d8b03aa` | `47b57f1`, `670e401`, `ec4e797` | lab: add count-driven mixed client cohorts |
| `bc4d824` | `a181543` | optimizer: preserve client cohort observations |
| `bb9285c` | `3671cef` | webui: distinguish IoT client cohort |
| `c6750a3` | `f7a1a0d` | tests: exercise mixed client cohorts under RF churn |
| `d3f6051` | `670e401` | hwsim: default direct lab pool to 32 radios |
| `02ba8e4` | `670e401` | lab: register mixed client pool with wmediumd once |
| `8368501` | `f7a1a0d` | tests: capture wmediumd resource and drop telemetry |
| `db466fe` | `3671cef`, `f7a1a0d` | webui: group clients inside expanded SSID bubbles |
| `2e7234b` | `3671cef`, `ec4e797`, `f7a1a0d` | webui: show live client signal in topology |
| `ec22992` | `3671cef`, `f7a1a0d` | webui: make topology movement and backhaul state observable |
| `ae05c8e` | `3671cef`, `f7a1a0d` | webui: expose exact backhaul parent links |
| `d182b33` | `3671cef`, `f7a1a0d` | webui: stabilize topology layout and show client channel |
| `d353c65` | `073a1d4`, `1ad0a7f`, `3671cef`, `e7062d4` | easymesh: make multi-hop state authoritative |
| `5280bb4` | `47b57f1`, `670e401`, `a181543`, `ec4e797`, `f7a1a0d` | lab: scale clients and validate multi-hop scenarios |
| `dd51b27` | `c67c804` | docs: record 20-client multi-hop acceptance |
| `565f66d` | `47b57f1` | vm: add verified fresh lab redeploy |
| `6b378c7` | `47b57f1` | vm: resize hwsim pool for accepted scale |
| `c558ab7` | `47b57f1` | vm: separate hwsim pool and node sizing |
| `660cf8c` | `47b57f1` | vm: reclaim stale hwsim interfaces at idle |
| `b78dfac` | `47b57f1` | vm: recover hwsim before lab dependencies |
| `c9e0dcf` | `c67c804`, `c987a39`, `e7062d4` | easymesh: recover stalled tri-band subdoc delivery |
| `b76bf87` | `c67c804`, `c987a39` | easymesh: serialize controller onboarding model |
| `b5ded8d` | `c67c804`, `c987a39` | easymesh: retry deferred tri-band subdocs |
| `d8f4386` | `c67c804`, `c987a39` | easymesh: service WSC recovery after orchestration |
| `a81670f` | `c67c804`, `c987a39` | easymesh: retain accepted WSC apply slot |
| `62d9284` | `c67c804`, `c987a39` | easymesh: keep retry M1 independent of command |
| `2d2cb6c` | `c67c804`, `c987a39` | easymesh: source retry M1 identity from model |
| `101086c` | `c987a39` | easymesh: preserve WSC recovery past device init |
| `036051f` | `c987a39` | easymesh: preserve WSC recovery past config renew |
| `e7bb669` | `c987a39` | easymesh: recover orphaned WSC subdocs |
| `a483114` | `c987a39` | easymesh: complete OneWifi callback at BSS config |
| `a9689eb` | `670e401` | lab: retry stalled WLAN client association |
| `8243f1e` | `1e68c34`, `aaa4d00` | wmediumd: add bounded observer telemetry |
| `0668ec9` | `670e401`, `d5a16fa`, `f7a1a0d` | webui: report extender signal freshness |
| `05bc6d3` | `47b57f1`, `670e401` | lab: recover warm-start client handoff race |
| `d4c7acf` | `aaa4d00` | tools: add wmediumd Console |
| `43f5556` | `47b57f1` | vm: package wmediumd Console |
| `14a22e1` | `670e401` | lab: resolve client bands from live AP channels |
| `fa67e32` | `47b57f1` | vm: wait for wmediumd Console readiness |
| `fb3bf7e` | `d5a16fa` | webui: package extender signal freshness helper |
| `f51d087` | `47b57f1`, `aaa4d00` | tools: publish wmediumd binary provenance safely |
| `8d1c49a` | `47b57f1` | vm: require fresh extender signal telemetry |
| `4ff8b4b` | `47b57f1`, `c67c804` | docs: document wmediumd Console acceptance |
| `3895d1f` | `d5a16fa`, `f7a1a0d` | webui: report mesh device backhaul signal |
| `9703300` | `aaa4d00`, `c67c804` | docs: record rev130 signal and Console acceptance |

