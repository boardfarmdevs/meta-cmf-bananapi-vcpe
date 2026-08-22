FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# Keep source patches in dependency order in one place. Comments below retain
# the evidence for each patch without silently changing application order.
EASYMESH_CORE_PATCHES = " \
    file://0001-ec_pa_configurator-fix-std-min-type-mismatch-on-32bit.patch \
    file://0002-securityTypeMap-WPA2-Personal-is-WPA2PSK-not-WPA2.patch \
    file://0003-topo-query-do-not-wait-for-disabled-radios.patch \
    file://0004-crypto-decrypt-final-block-into-the-callers-buffer.patch \
    file://0005-fix-heap-overflow-building-the-btm-request-action-frame.patch \
    file://0006-tests-honor-caller-supplied-googletest-filter.patch \
    file://0007-steering-serialize-request-entirely-from-command-params.patch \
    file://0008-tests-add-steering-request-serializer-regression-tests.patch \
    file://0009-steering-restore-state-after-client-steering.patch \
    file://0010-agent-send-BTM-request-on-the-source-VAP.patch \
    file://0011-em_configuration-6ghz-upgrade-guard-match-wpa2psk.patch \
    file://0011-steering-route-1905-ACK-to-the-requesting-radio.patch \
    file://0012-agent-subscribe-all-AP-action-frame-Rx.patch \
    file://0013-steering-acknowledge-and-complete-BTM-report.patch \
    file://0015-cli-steer-sta-send-the-callers-request.patch \
    file://0016-net-node-size-tree-string-buffer.patch \
    file://0017-dm-enforce-single-association-invariant.patch \
    file://0018-al-sap-retry-registration-during-1905-startup.patch \
    file://0019-agent-exclude-disabled-radio-from-onboarding.patch \
    file://0021-agent-resend-m1-on-lost-m2.patch \
    file://0022-ctrl-elect-active-topology-query-radio.patch \
    file://0023-wsc-refresh-registrar-key-per-m1.patch \
    file://0024-agent-send-sta-topology-notify-synchronously.patch \
    file://0025-controller-size-sta-frame-body-hex-buffer.patch \
    file://0026-orch-complete-cancelled-commands-independently.patch \
    file://0027-metrics-size-ap-response-for-model.patch \
    file://0028-cli-topology-layout-and-export.patch \
    file://0029-cli-release-native-tree-allocations.patch \
    file://0030-db-drain-result-sets-before-early-return.patch \
    file://0031-association-refresh-topology-before-publish.patch \
    file://0032-sta-decode-reassociation-capabilities.patch \
    file://0033-sta-retain-capability-on-empty-roam-report.patch \
    file://0034-cli-serialize-native-command-execution.patch \
    file://0035-cli-remove-unused-command-data-model-init.patch \
    file://0036-controller-release-json-output.patch \
    file://0037-cli-serve-live-device-client-inventory.patch \
    file://0038-cli-refresh-topology-on-live-change.patch \
    file://0039-cli-identify-and-enlarge-topology-stas.patch \
    file://0040-cli-preserve-active-topology-drag.patch \
    file://0041-cli-enlarge-topology-network-labels.patch \
    file://0042-metrics-enable-policy-ack-profile-and-persistence.patch \
    file://0043-cli-apply-policies-per-device.patch \
    file://0044-cli-expose-live-client-rcpi.patch \
    file://0045-cli-overlay-live-clients-on-topology.patch \
    file://0046-al-sap-preserve-stream-message-boundaries.patch \
    file://0047-controller-reconcile-topology-notification-liveness.patch \
    file://0048-controller-update-metrics-only-for-current-stas.patch \
    file://0049-cli-bound-controller-command-transport.patch \
    file://0050-cli-reject-empty-controller-topology.patch \
    file://0051-controller-commit-association-before-capability-query.patch \
    file://0052-topology-response-reconcile-associated-clients.patch \
    file://0053-manager-service-timers-under-event-load.patch \
    file://0054-controller-serialize-command-result-sessions.patch \
    file://0055-topology-response-do-not-overwrite-conflicting-owner.patch \
    file://0056-radio-service-protocol-timers-under-frame-load.patch \
    file://0057-cli-render-topology-without-mutating-model.patch \
    file://0058-cli-isolate-d3-topology-render-state.patch \
    file://0059-cli-optimize-rendered-topology-nodes.patch \
    file://0060-metrics-create-defaults-for-reloaded-radios.patch \
    file://0061-cli-enable-all-metrics-reporting.patch \
    file://0062-controller-preserve-profile-through-dm-commit.patch \
    file://0063-controller-commit-topology-response-profile.patch \
    file://0064-metrics-report-cpe-and-client-uptime.patch \
    file://0065-cli-source-client-association-from-sta-model.patch \
    file://0066-controller-synchronize-runtime-agent-profile.patch \
    file://0067-controller-replay-explicit-policy.patch \
    file://0068-cli-expose-live-bss-inventory.patch \
    file://0069-candidate-rcpi-complete-unassociated-transaction.patch \
    file://0070-agent-accept-onewifi-nasta-response.patch \
    file://0071-agent-correlate-candidate-metrics-response.patch \
    file://0072-metrics-preserve-associated-report-receipt-time.patch \
    file://0073-wsc-retry-with-fresh-enrollee-transaction.patch \
    file://0074-candidate-metrics-store-on-correlated-radio.patch \
    file://0075-cli-key-topology-radio-tree-by-name.patch \
    file://0076-controller-complete-candidate-command-on-response.patch \
    file://0077-cli-join-topology-to-authoritative-radio-inventory.patch \
    file://0078-topology-response-resolve-owner-by-association-age.patch \
    file://0079-cli-distinguish-iot-clients.patch \
    file://0080-cli-place-clients-inside-ssid-bubbles.patch \
    file://0081-cli-show-live-client-signal-in-topology.patch \
    file://0082-cli-drag-clients-and-highlight-steering.patch \
    file://0083-cli-show-authoritative-backhaul-channel.patch \
"
SRC_URI += "${EASYMESH_CORE_PATCHES}"

# std::min(WIFI_MTU_SIZE, len - offset) type mismatch on 32-bit x86, where size_t
# (unsigned int) and WIFI_MTU_SIZE's unsigned long are distinct types - see patch
# header. This project's usual targets (64-bit/arm64) don't hit it since size_t is
# unsigned long there too.

# 6 GHz WSC-M2 auth-upgrade guard also matches EM_AUTH_WPA2PSK (see patch header):
# NetworkSSIDList "WPA2 Personal" -> 0x20 (not 0x10) via 0002-securityTypeMap, so the 6 GHz
# M2 wrongly carried WPA2-PSK; the leaf's encode_security_object() then rejects it. Lets a
# WPA2 backhaul coexist with a WPA3/SAE 6 GHz fronthaul (guard upgrades 6 GHz only).
# A multi-radio extender runs WSC for all radios at once; the controller sends each M2
# only once and never retransmits, so a single lost/mistimed M2 strands one radio in
# wsc_m2_pending -- its VAP subdoc is never pushed, wifi_hal_createVAP is never called,
# and that fronthaul radio never beacons (random "straggler" on fresh onboarding). The
# agent now re-sends M1 (bounded) while waiting, and the controller re-issues M2.
# When several radios reach topo_sync_pending together, the vector-front radio may
# already have left the active em_config candidate set. Elect an active candidate
# to send the Topology Query so the device's BSSList cannot remain unpopulated.
# A WSC M1 retransmission must create a new registrar transaction.  Reusing a
# registrar DH key that OpenSSL has rejected makes every bounded M1 retry fail
# identically and leaves that radio permanently unconfigured.

# A live association can arrive while an extender radio is still finishing AP
# capability/topology synchronization.  Permit this fire-and-forget STA-list
# command during onboarding, send it synchronously, and restore the prior radio
# state so the event cannot expire or disrupt the onboarding exchange.

# AL-SAP is a length-delimited protocol carried over SOCK_STREAM.  Read one
# complete framed SDU at a time; a plain recv() can coalesce adjacent topology
# notifications and the old deserializer silently discarded every SDU after
# the first one in that read.

# A 512-byte association frame needs 1025 bytes when stored as hexadecimal plus
# NUL.  The old 1024-byte scratch buffer made hex() reject the maximum-sized
# frame and fed uninitialized data to SQL, dropping that client from STAList.

# The account/database creation in setup_mysql_db_pre.sh (run from em_ctrl.service's
# ExecStartPre) is guarded by /nvram/mysql_db_account_exists, but the MariaDB datadir lives
# in the container's ephemeral rootfs while /nvram is a persistent volume. After any
# redeploy the marker survives and the database does not, so the guard skips creation
# forever: em_ctrl then comes up against a nonexistent database, logs table errors, never
# answers AP-Autoconfiguration Search, and the mesh silently fails to form. Guard on the
# database actually being reachable instead of on the marker. The marker is still written
# so anything else looking for it is unaffected.
#
# NOTE on the AL-MAC comparison a few lines above that guard: it reads eth1_virt_peer and
# compares against NetworkList.ColocatedAgentID to detect "SD card moved to a new board".
# setup_mysql_db_post.sh seeds that column from eth0_virt_peer, which looks like a
# mismatch, but em_ctrl rewrites the row at runtime with the colocated agent's real AL MAC
# -- and the colocated agent is the one bound to eth1_virt_peer (see
# ieee1905_em_agent.service). Confirmed on a running controller: eth1_virt_peer is
# 00:60:2f:c9:00:d7 and the steady-state ColocatedAgentID is 00:60:2f:c9:00:d7, while
# eth0_virt_peer is ...:c7. So eth1_virt_peer is correct and must be left alone; "fixing"
# it to match post.sh's seed makes the comparison mismatch on every single start and drops
# the database each time.
do_install_append() {
    f="${D}${sysconfdir}/../usr/ccsp/EasyMesh/setup_mysql_db_pre.sh"
    [ -f "$f" ] || f="${D}/usr/ccsp/EasyMesh/setup_mysql_db_pre.sh"
    if [ -f "$f" ]; then
        sed -i 's@^if \[ ! -e "/nvram/mysql_db_account_exists" \]; then@if ! mysql -u bpi --password="root" -e "use OneWifiMesh;" >/dev/null 2>\&1; then@' "$f"
        bbnote "meta-cmf-bananapi-vcpe: fixed spurious DB drop + stale-marker guard in setup_mysql_db_pre.sh"
    fi
}

# The stock colocated and extender agent units background onewifi_em_agent from
# a shell under Type=forking and append all output to /tmp/em_agent.log.  There
# is no PID file, so systemd reports MainPID=0 and cannot reliably stop, restart,
# or account for the actual agent.  The log is on tmpfs and reached tens of MiB
# during a short lab run, directly consuming the embedded memory budget.
#
# onewifi_em_agent is a normal foreground process (it does not sd_notify), so
# run it as Type=simple and send output to the bounded journal.  Apply this to
# both controller-colocated and extender variants after their variant-specific
# prerequisite edits above.
do_install_append() {
    f="${D}${systemd_unitdir}/system/em_agent.service"
    if [ -f "$f" ]; then
        if grep -q '^ExecStart=.*onewifi_em_agent.*em_agent\.log' "$f"; then
            sed -i 's|^ExecStart=.*onewifi_em_agent.*$|ExecStart=/usr/bin/onewifi_em_agent|' "$f"
        elif ! grep -q '^ExecStart=/usr/bin/onewifi_em_agent$' "$f"; then
            bbfatal "meta-cmf-bananapi-vcpe: unexpected em_agent.service ExecStart"
        fi

        sed -i 's/^Type=forking$/Type=simple/' "$f"
        sed -i '/^StandardOutput=/d; /^StandardError=/d; /^SyslogIdentifier=/d; /^LogRateLimitIntervalSec=/d; /^LogRateLimitBurst=/d' "$f"
        sed -i '/^ExecStart=\/usr\/bin\/onewifi_em_agent$/a StandardOutput=journal\
StandardError=journal\
SyslogIdentifier=onewifi_em_agent\
LogRateLimitIntervalSec=30s\
LogRateLimitBurst=1000' "$f"
        grep -q '^RestartSec=' "$f" || sed -i '/^Restart=always/a RestartSec=3' "$f"

        grep -q '^Type=simple$' "$f" || bbfatal "meta-cmf-bananapi-vcpe: failed to make em_agent foreground"
        ! grep -q '/tmp/em_agent\.log' "$f" || bbfatal "meta-cmf-bananapi-vcpe: unbounded em_agent log remains"
        bbnote "meta-cmf-bananapi-vcpe: em_agent is foregrounded and uses bounded journald"
    fi
}

# setup_mysql_db_post.sh is built, installed to /usr/ccsp/EasyMesh and then never invoked
# by anything -- no systemd unit, no other script references it. It is what populates
# NetworkSSIDList/NetworkList, i.e. the SSIDs and passphrases the controller hands a leaf
# in WSC M2, so without it the controller answers AP-Autoconfiguration with nothing to
# configure and no fronthaul VAP is ever created on the leaf.
#
# It cannot run from ExecStartPre: it INSERTs into tables that em_ctrl itself creates
# during startup. Hence "post" -- but em_ctrl.service is Type=forking with the real binary
# backgrounded inside `sh -c '... &'`, so systemd considers the unit started almost
# immediately and an ExecStartPost would fire long before the schema exists. Wait for the
# table to appear first, then run it; bounded so a genuinely broken DB can't wedge boot.
#
# Its internal /nvram/mysql_db_data_exists guard has the same stale-marker defect as the
# account guard (see the do_install_append above): /nvram persists across redeploys while
# MariaDB's datadir does not, so after a redeploy the marker suppresses the insert into an
# empty database forever. Guard on the table actually having rows instead.
do_install_append() {
    f="${D}/usr/ccsp/EasyMesh/setup_mysql_db_post.sh"
    if [ -f "$f" ]; then
        sed -i 's@^if \[ ! -e "/nvram/mysql_db_data_exists" \]; then@n=$(mysql -u bpi --password="root" -D OneWifiMesh -sN -e "select count(*) from NetworkSSIDList;" 2>/dev/null); if [ "${n:-0}" = "0" ]; then@' "$f"
        bbnote "meta-cmf-bananapi-vcpe: replaced stale-marker guard in setup_mysql_db_post.sh"
    fi
    u="${D}${systemd_unitdir}/system/em_ctrl.service"
    if [ -f "$u" ] && ! grep -q setup_mysql_db_post "$u"; then
        sed -i "\@^ExecStart=@a ExecStartPost=/bin/sh -c 'i=0; while [ \$i -lt 60 ]; do mysql -u bpi --password=\"root\" -D OneWifiMesh -e \"select 1 from NetworkSSIDList limit 1;\" >/dev/null 2>&1 \&\& break; i=\$((i+1)); sleep 2; done; /usr/ccsp/EasyMesh/setup_mysql_db_post.sh || true'" "$u"
        bbnote "meta-cmf-bananapi-vcpe: wired setup_mysql_db_post.sh into em_ctrl.service"
    fi
}

# Two ordering/robustness defects that only show up on a cold boot, both observed on a
# freshly redeployed controller.
#
# 1. onewifi_em_ctrl aborts outright if the 1905 control socket isn't there yet:
#
#      terminate called after throwing an instance of 'AlServiceException'
#        what():  Failed to connect to Unix socket for control
#      em_ctrl.service: Main process exited, code=dumped, status=6/ABRT
#
#    em_ctrl.service already declares After=ieee1905_em_ctrl.service, but that unit is
#    Type=forking with its ExecStart backgrounded inside `sh -c '... &'`, so the shell
#    exits immediately and systemd considers it started long before /usr/bin/ieee1905 has
#    created /tmp/al_em_ctrl_control_socket. The ordering is therefore satisfied while the
#    socket still does not exist. Only Restart=always eventually got em_ctrl up, after a
#    burst of core dumps -- which is what "Start request repeated too quickly" plus
#    "Failed with result 'core-dump'" in the journal was, and why the crash looked
#    intermittent and refused to reproduce under a deliberate restart. Wait for the socket
#    itself rather than for the unit state.
#
# 2. setup_mysql_db_pre.sh's "AL MAC changed -> wipe the database" check reads the current
#    AL MAC from an interface that ieee1905_em_ctrl.service creates, and on a cold boot
#    this ExecStartPre runs first:
#
#      ifconfig: eth0_virt_peer: error fetching interface information: Device not found
#
#    so Present_al_mac comes back empty. Compared against a populated NetworkList that is
#    a mismatch, and the branch drops the entire OneWifiMesh database -- destroying the
#    mesh configuration for a reason that is purely a startup race.
#
#    Worse, there is no single correct interface to read. setup_mysql_db_post.sh seeds
#    ColocatedAgentID from eth0_virt_peer while this check reads eth1_virt_peer, and which
#    of the two veth peers ends up with which MAC is not stable across boots -- the same
#    container was observed with ColocatedAgentID = ...:d7 (matching eth1_virt_peer) after
#    one boot and ...:c7 (matching eth0_virt_peer) after another, with the stored value
#    otherwise steady. Pinning the check to either interface therefore guarantees a
#    spurious mismatch on some boots, and each one drops the database and forces a full
#    repopulate -- which also crashed em_ctrl when it happened underneath a starting
#    instance.
#
#    Require that the AL MAC could be read at all, and treat it as changed only when the
#    stored value matches neither veth peer. A genuinely different board still matches
#    neither, so the "SD card moved" detection this implements is preserved.
do_install_append() {
    f="${D}/usr/ccsp/EasyMesh/setup_mysql_db_pre.sh"
    if [ -f "$f" ]; then
        sed -i '/^Present_al_mac=/a Present_al_mac_alt=`ifconfig eth0_virt_peer | grep HWaddr | cut -d " " -f6 | tr "[:upper:]" "[:lower:]"`' "$f"
        sed -i 's@^if \[ "$Present_al_mac" != "$Existing_al_mac" \] ||@if ( [ -n "${Present_al_mac}${Present_al_mac_alt}" ] \&\& [ "$Present_al_mac" != "$Existing_al_mac" ] \&\& [ "$Present_al_mac_alt" != "$Existing_al_mac" ] ) ||@' "$f"
        bbnote "meta-cmf-bananapi-vcpe: pre.sh only wipes when the DB AL MAC matches neither veth peer"
    fi
    u="${D}${systemd_unitdir}/system/em_ctrl.service"
    if [ -f "$u" ] && ! grep -q al_em_ctrl_control_socket "$u"; then
        sed -i "\@^ExecStartPre=@i ExecStartPre=/bin/sh -c 'i=0; while [ ! -e /tmp/al_em_ctrl_control_socket ] \&\& [ \$i -lt 90 ]; do i=\$((i+1)); sleep 1; done'" "$u"
        bbnote "meta-cmf-bananapi-vcpe: em_ctrl.service now waits for the 1905 control socket"
    fi
    # The socket-existence wait above fixes the cold-boot case (verified: em_ctrl reaches
    # active with NRestarts=0 and no core dump). It cannot fix a restart, where the socket
    # file is already there but connect() still fails for a moment because the outgoing
    # instance has not released its end yet -- libalsap throws AlServiceException("Failed
    # to connect to Unix socket for control"). Patch 0018 catches that exception at the
    # controller/agent registration boundary and retries the complete registration for a
    # bounded interval. Keep a modest RestartSec as a final fallback if ieee1905 never
    # becomes ready, so a clean registration failure cannot create a restart storm.
    if [ -f "$u" ] && ! grep -q '^RestartSec=' "$u"; then
        sed -i '/^Restart=always/a RestartSec=5' "$u"
        bbnote "meta-cmf-bananapi-vcpe: em_ctrl.service RestartSec=5 to stop the restart-crash burst"
    fi
}

# The upstream controller unit backgrounds the real process from a shell and
# appends stdout forever to /tmp/em_ctrl.log. /tmp is tmpfs in the LXC image,
# so normal topology publication grew that file by about 39 KiB/s and charged
# the entire file to the container memory cgroup. A 1 GiB controller eventually
# OOM-killed MariaDB and em_ctrl; increasing the limit only delayed recurrence.
#
# Keep stdout available, but make systemd own the foreground process and route
# both streams through the already-bounded volatile journal (16 MiB in this
# image). Per-unit rate limiting also prevents verbose topology dumps from
# spending unbounded CPU in journald while retaining useful protocol context.
do_install_append() {
    u="${D}${systemd_unitdir}/system/em_ctrl.service"
    if [ -f "$u" ]; then
        if grep -q '^ExecStart=.*onewifi_em_ctrl.*em_ctrl\.log' "$u"; then
            sed -i 's|^ExecStart=.*onewifi_em_ctrl.*$|ExecStart=/usr/bin/onewifi_em_ctrl bpi@root|' "$u"
        elif ! grep -q '^ExecStart=/usr/bin/onewifi_em_ctrl bpi@root$' "$u"; then
            bbfatal "meta-cmf-bananapi-vcpe: unexpected em_ctrl.service ExecStart"
        fi

        sed -i 's/^Type=forking$/Type=simple/' "$u"
        sed -i '/^StandardOutput=/d; /^StandardError=/d; /^SyslogIdentifier=/d; /^LogRateLimitIntervalSec=/d; /^LogRateLimitBurst=/d' "$u"
        sed -i '/^ExecStart=\/usr\/bin\/onewifi_em_ctrl bpi@root$/a StandardOutput=journal\
StandardError=journal\
SyslogIdentifier=onewifi_em_ctrl\
LogRateLimitIntervalSec=30s\
LogRateLimitBurst=1000' "$u"

        grep -q '^Type=simple$' "$u" || bbfatal "meta-cmf-bananapi-vcpe: failed to make em_ctrl foreground"
        ! grep -q '/tmp/em_ctrl\.log' "$u" || bbfatal "meta-cmf-bananapi-vcpe: unbounded em_ctrl log remains"
        bbnote "meta-cmf-bananapi-vcpe: em_ctrl stdout/stderr now use bounded journald"
    fi
}

# setup_mysql_db_post.sh seeds every haul in NetworkSSIDList as AuthType 'WPA3 Personal'
# with MFPConfig 'Required'. em_ctrl pushes that to OneWifi, so the controller's VAPs come
# up as SAE with management frame protection required:
#
#   update_security_config:679: security:512 mfp:2 wpa_key_mgmt:67109888 11w:2
#
# But ccsp-one-wifi is built with -DHWSIM_RADIO here, and its patches 0005/0007 deliberately
# downgrade both the AP-side and STA-side security defaults from wpa3_personal to WPA2
# because mac80211_hwsim does not carry the SAE/MFP setup reliably in this environment.
# The controller's backhaul AP therefore advertised WPA3/SAE while the leaf's mesh STA
# offered WPA2, and the 4-way handshake could never complete: both ends sent EAPOL, neither
# accepted the other's, and the AP eventually gave up --
#
#   leaf: EAPOL: Supplicant port status: Unauthorized
#   leaf: nl80211_disconnect_event: reason code:15          (4-Way Handshake Timeout)
#   ctrl: wifi_drv_hapd_send_eapol: eapol_timeout callback is called
#   ctrl: wifi_drv_sta_deauth: Enter 02:00:00:d8:b7:19 15
#
# in a loop, which also meant the STA never reached WPA_COMPLETED and so was never enslaved
# into brlan0 (that only happens on WPA_COMPLETED), leaving the leaf with no data path.
#
# This never surfaced before because nothing invoked post.sh -- the rows simply did not
# exist, and the backhaul AP fell back to the same HWSIM_RADIO WPA2 defaults as the STA.
# Wiring post.sh up (see above) is what exposed the disagreement. Seed the rows to match
# what the rest of this build actually negotiates. Scoped to the vcpe container layer, so
# real BananaPi R4 hardware keeps upstream's WPA3 defaults.
#
# Capability gate (review P1 #3, controller side): this rewrite exists ONLY to match the
# HWSIM_RADIO WPA2 downgrade that ccsp-one-wifi patches 0005/0007 apply. Those patches are
# now gated `!(HWSIM_RADIO && !HWSIM_6GHZ_CAPABLE)`, so a HWSIM_6GHZ_CAPABLE build restores
# the WPA3/SAE/MFP-required local defaults. The controller's seeded NetworkSSIDList must be
# gated the SAME way, or the two security sources disagree: OneWifi local = SAE while the
# controller's WSC M2 (built from these rows) = WPA2 -- which is wrong for 6 GHz (SAE-H2E +
# PMF mandatory) and would reproduce the AP/STA mismatch on the extender's wifi2. So skip
# the downgrade when 6 GHz is enabled: seed stays WPA3/SAE, matching the restored defaults,
# so M2 carries standards-correct 6 GHz security end to end.
HWSIM_6GHZ_CAPABLE ??= "0"
do_install_append() {
    f="${D}/usr/ccsp/EasyMesh/setup_mysql_db_post.sh"
    if [ -f "$f" ]; then  # B+C: always seed WPA2 (guard upgrades 6 GHz fronthaul)
        sed -i "s@'WPA3 Personal'@'WPA2 Personal'@g; s@'Required'@'Optional'@g" "$f"
        bbnote "meta-cmf-bananapi-vcpe: post.sh seeds WPA2/MFP-optional to match the HWSIM_RADIO defaults"
    elif [ -f "$f" ]; then
        bbnote "meta-cmf-bananapi-vcpe: HWSIM_6GHZ_CAPABLE=1 -- keeping post.sh WPA3/SAE seed to match restored defaults (M2 6GHz security)"
    fi
}

# Same unbounded-wait problem as ieee1905-em.bbappend's do_install_append (see there for
# the full rationale): ext_em_agent.service (installed as em_agent.service) also calls
# setup_ext_pre.sh, which blocks forever waiting for a VAP matching AL_MAC_ADDR to report
# both a channel and an ssid. On a cold leaf those fronthaul VAPs don't exist until the
# controller has answered AP-Autoconfiguration and pushed WSC M2 -- and em_agent is what
# drives that exchange, so waiting on it here is circular. Bound it and continue.
do_install_append() {
    # Only the em_extender variant (ext_em_agent.service, installed under this name) calls
    # setup_ext_pre.sh. The controller installs its own em_agent.service for the colocated
    # agent, which has neither that ExecStartPre nor a backhaul to wait for -- so key off
    # the script reference rather than the file name, or the controller's colocated agent
    # would sit in the wait below for no reason.
    f="${D}${systemd_unitdir}/system/em_agent.service"
    if [ -f "$f" ] && grep -q setup_ext_pre "$f"; then
        sed -i "s@ExecStartPre=/bin/sh -c '/usr/ccsp/EasyMesh/setup_ext_pre.sh'@ExecStartPre=/bin/sh -c 'timeout 60 /usr/ccsp/EasyMesh/setup_ext_pre.sh || true'@" "$f"
        bbnote "meta-cmf-bananapi-vcpe: bounded setup_ext_pre.sh in em_agent.service"
    fi
    # em_agent sends its AP-Autoconfiguration Search almost immediately after starting and
    # cancels dev_init roughly a second later if nothing answers -- it never retries the
    # search afterwards. On a cold leaf that deadline routinely expires before the backhaul
    # is usable: observed the search sent at 04:19:35 and dev_init cancelled at 04:19:36,
    # while the controller only finished enslaving the WDS station interface (and so only
    # became reachable) at 04:20:16. The leaf then sat with a perfectly good, associated,
    # bridged backhaul and no configuration, and needed a manual `systemctl restart
    # em_agent` to try again.
    #
    # Hold the unit until a station-mode interface is both associated and a bridge port,
    # which is exactly the condition for its 1905 frames to reach the controller. Bounded,
    # and deliberately exits 0 on timeout so a leaf that never gets a backhaul still starts
    # the agent rather than failing the unit.
    # Extender only, for the same reason the bounded setup_ext_pre above is: the
    # controller installs this unit for its colocated agent, which has no backhaul
    # to wait for and never will -- no station-mode interface on the controller is
    # ever associated. Without the setup_ext_pre test this wait was applied there
    # too, where it can never be satisfied, so the colocated agent burned the full
    # 300s timeout on every start and never ran long enough to configure the
    # controller's own radios.
    if [ -f "$f" ] && grep -q setup_ext_pre "$f" && ! grep -q phy80211 "$f"; then
        sed -i "\@^ExecStart=@i ExecStartPre=/bin/sh -c 'i=0; while [ \$i -lt 150 ]; do for d in /sys/class/net/*/phy80211; do n=\$(basename \$(dirname \$d)); if iw dev \"\$n\" link 2>/dev/null | grep -q \"Connected to\" && [ -e \"/sys/class/net/\$n/master\" ]; then exit 0; fi; done; i=\$((i+1)); sleep 2; done; exit 0'" "$f"
        bbnote "meta-cmf-bananapi-vcpe: em_agent.service waits for a bridged backhaul before starting"
    fi
    # OneWifi holds its own fronthaul/radio configuration only in memory: it is pushed to it,
    # subdoc by subdoc, over the RBUS "webconfig" SOUTH channel by em_agent as WSC M2s are
    # applied. When OneWifi is restarted (Restart=always, a crash, or a manual restart) it comes
    # back with every subdoc at version 0 and no VAP config. In a full RDK-B stack the WebConfig
    # framework daemon answers OneWifi's post-crash "notifyVersion_to_Webconfig" (an RBUS
    # webconfigSignal set) by re-delivering the cached blobs; this EasyMesh image ships no such
    # daemon, so that set fails "Entry not found" and nobody re-pushes. em_agent -- the actual
    # config source here -- neither registers that signal nor observes the restart, so the leaf's
    # fronthaul (incl. 6 GHz) stays down after a OneWifi restart until em_agent is restarted by
    # hand and re-drives onboarding -> M2 -> the SOUTH push. Couple the two units so a OneWifi
    # restart propagates to em_agent, which then re-applies the configuration on its own; its
    # ExecStartPre already waits for the backhaul to reassociate and rebridge first. Extender only
    # (setup_ext_pre marker), matching the two edits above -- the controller's colocated agent
    # configures the controller's own radios and has no separate OneWifi restart to track this way.
    if [ -f "$f" ] && grep -q setup_ext_pre "$f" && ! grep -q "PartOf=onewifi" "$f"; then
        sed -i "\@^After=@a PartOf=onewifi.service" "$f"
        bbnote "meta-cmf-bananapi-vcpe: em_agent.service PartOf=onewifi.service (re-push config on OneWifi restart)"
    fi
}

# The extender's AL (1905) MAC is derived by setup_veth_for_em.sh: it seeds the MAC of
# eth1_virt_peer -- which the ieee1905 daemon then reports as the agent AL MAC -- by
# offsetting a "primary" interface address (+0x20 on the default path). The lookup order
# is erouter0, then lan0, then /sys/class/ieee80211/phy0/macaddress. An extender container
# has neither erouter0 nor lan0, so it falls through to phy0 -- but the moved-in hwsim
# radio enumerates as phyN (e.g. phy27), never phy0, so that read fails, base_addr is
# empty, and $((0x + 0x20)) collapses to the SAME placeholder AL MAC 00:00:00:00:00:20 on
# every instance. Two `mv.sh -i` extenders then share one 1905 identity: the second
# onboards as a duplicate, and given the pre-upstream-PR#739 RUID/identity-based
# Topology-Response dispatch in em_ctrl (device-scoped CMDUs are keyed on the radio RUID,
# not the sender AL MAC) this corrupts the controller's data model -- both extenders' BSSes
# vanish and BSSList regresses to a single agent's -- in a way that persists even after the
# MAC is corrected by hand. Proven by a clean ordered bring-up: give the second extender a
# distinct AL MAC *before* it registers and BSSList reaches 10 x agents and holds, with no
# dispatch drops. wlan0 (the raw radio netdev LXD moves in) is present from boot and
# carries the radio's unique MAC, so prefer it over the non-existent phy0. On real BananaPi
# R4 hardware erouter0/lan0 exist and are still used first, so this only changes the
# container case. Scoped to this vcpe layer.
#
# Identity atomicity (review P1 #1): deriving the AL MAC from wlan0 on *every* boot
# tied it to the hwsim phy, but the radio RUIDs persist in /nvram -- two different
# lifecycles. On a normal redeploy the pool allocator can hand back a *different*
# phy, so the AL MAC changes while the RUIDs do not => the proven "new AL-MAC + old
# RUIDs" onboarding blocker (Issue B). Fix: make /nvram the single source of truth
# for both. The base MAC is seeded from wlan0 on the *first* boot and persisted to
# /nvram/em_al_base_mac; every later boot reads the persisted value, so the AL MAC is
# stable across a normal redeploy regardless of which phy was allocated. `bpi.sh -F`
# wipes the /nvram volume, so the AL MAC *and* the RUIDs regenerate together on a
# fresh baseline -- the {AL-MAC, RUID-set} tuple is now preserved-or-regenerated as a
# unit instead of drifting with pool allocation.
do_install_append() {
    f="${D}/usr/ccsp/EasyMesh/setup_veth_for_em.sh"
    if [ -f "$f" ]; then
        sed -i 's@base_addr="$(cat /sys/class/ieee80211/phy0/macaddress)"@if [ -s /nvram/em_al_base_mac ]; then base_addr="$(cat /nvram/em_al_base_mac)"; elif [ -e /sys/class/net/wlan0/address ]; then base_addr="$(cat /sys/class/net/wlan0/address)"; echo "$base_addr" > /nvram/em_al_base_mac 2>/dev/null; else base_addr="$(cat /sys/class/ieee80211/phy0/macaddress)"; fi@' "$f"
        sed -i 's@primary_addr="$(cat /sys/class/ieee80211/phy0/macaddress)"@if [ -s /nvram/em_al_base_mac ]; then primary_addr="$(cat /nvram/em_al_base_mac)"; elif [ -e /sys/class/net/wlan0/address ]; then primary_addr="$(cat /sys/class/net/wlan0/address)"; echo "$primary_addr" > /nvram/em_al_base_mac 2>/dev/null; else primary_addr="$(cat /sys/class/ieee80211/phy0/macaddress)"; fi@' "$f"
        bbnote "meta-cmf-bananapi-vcpe: setup_veth_for_em.sh derives the extender AL MAC from a /nvram-persisted base (seeded from wlan0 on first boot) so identity is stable across redeploy and regenerated by bpi.sh -F"
    fi
}

# THE reason the EasyMesh backhaul never recovered after autoconfiguration: the
# securityTypeMap entry for "WPA2 Personal" points at EM_AUTH_WPA2 (0x0010, which is
# WPA2-Enterprise in WSC) instead of EM_AUTH_WPA2PSK (0x0020). The controller therefore
# encodes Enterprise into WSC M2, the agent turns that into security mode 512
# (wpa3_personal) instead of 16, and the mesh STA is reconfigured for SAE against a
# WPA2-PSK AP. sme_send_authentication() then fails silently -- no auth frame is ever
# sent, the AP sees only probe requests, and the STA retries forever. Only reachable
# because this build forces WPA2 for mac80211_hwsim; upstream's WPA3 Personal default maps
# correctly. See patch header.

# The agent refuses to answer a Topology Query until every one of its radios has
# reached bssconfig_ind. The 6GHz radio is disabled here (ccsp-one-wifi patch 0006,
# because every 6GHz channel is no-IR under this host's regulatory domain), so it
# never gets there and the agent never sends a Topology Response at all -- 40+
# queries answered with nothing on both agents. Since the AP Operational BSS TLV
# rides in that response, the controller's BSSList stays empty for every radio,
# no station is ever attributed to a BSS, and steer_sta cannot work. Skip disabled
# radios rather than blocking on them. See patch header.

# platform_cipher_decrypt() discards the last block of every decryption and still
# counts it as valid plaintext. With padding enabled (which AES-128-CBC callers
# use) EVP_DecryptUpdate holds the final block back, and EVP_DecryptFinal_ex was
# handed a local scratch buffer instead of the caller's -- so, decryption being
# in-place, those bytes keep the raw ciphertext while the returned length says
# they are plaintext. In WSC M2 the MAC Address attribute straddles that
# boundary, so the agent decoded fronthaul radio MACs whose first three bytes
# were correct and last three were ciphertext -- matching no interface, yet
# always starting 02:00:00, which is what made them look like plausible MACs.
# Generic crypto defect, all platforms, every caller. See patch header.

# THE reason EasyMesh client steering never worked: the agent ABORTS on every
# steer. analyze_btm_request_action_frame() sizes its buffer for the action
# payload ('len') but builds that payload through an ieee80211_mgmt overlay whose
# u.action member sits 24 bytes in, after the 802.11 header -- so it writes 24
# bytes past the allocation and corrupts the heap. glibc aborts at the next
# allocation, which is the very next em_printfout, so the process dies with
# SIGABRT before any BTM Request reaches OneWifi. Measured: ALLOC=44, last byte
# written at offset 68, OVERFLOW=24. Size the allocation for the overlay; 'len',
# frame_len and the memcpy are correct as they stand and are left alone.
# Platform-independent -- nothing here is hwsim- or container-specific.


# The controller rewrote the source BSSID of every Steering Request. The TLV
# builder took every field from the command's steer params except req->bssid,
# which it read from get_data_model()->m_bss[0] -- so a client on the extender's
# 5GHz VAP (02:00:00:87:f8:50) went out on the wire with that agent's 2.4GHz VAP
# (02:00:00:6e:a9:a5), and the agent then transmitted from the radio the client
# was not associated with. Extracting a stateless, parameter-driven serializer
# fixes it and removes the data model from reach, so it cannot come back. Also
# zeroes the reserved nibble (previously whatever the caller's buffer held) and
# byte-swaps the steering opportunity window, which was the only two-octet field
# in the TLV not being htons()'d. Platform-independent.

# Regression tests for the serializer above, and the test-runner fix needed to
# actually run them: tests/main.cpp installed its built-in negative filter after
# InitGoogleTest() had already parsed --gtest_filter, so no subset could ever be
# selected and every run executed all ~2900 tests -- aborting inside unrelated
# pre-existing failures long before reaching these seven. Both are test-only;
# the test target stays behind EM_UNITTEST, which is false for shipped images.

# Client steering must remain eligible after the controller reaches topology
# synchronized, and completion or cancellation must restore the displaced
# stable state instead of leaving the radio pending or forcing configured.

# Build and transmit a valid BTM Request from the request's actual source VAP.

# Generic 1905 ACKs do not identify a radio. Correlate the steering request MID
# across the source agent's radios so the ACK reaches the radio which sent it.

# BTM responses arrive on the source fronthaul VAP. Subscribe to action-frame
# receive events on every AP-mode BSS instead of only the first backhaul AP.

# Complete BTM-report orchestration with the protocol-required 1905 ACK and
# route that ACK by MID to the radio which has the report pending.

# A commanded (scripted/UI) client steer could not be triggered from the CLI at
# all on this build -- two libemcli bugs, plus a heap overflow that aborted it:
#   0015 steer_sta ignored the caller's ClientSteer params and scraped the whole
#        get_sta network dump instead, so the controller got no steer target and
#        emitted no Client Steering Request; and get_edited_node() aliased+freed a
#        subtree the caller still owned (a double free). Use net_node like the
#        other setters, and clone in both get_edited_node branches.
#   0016 get_network_tree_string() serialized the tree into a 16KB buffer with
#        mis-bounded strncat()s; a 3-device get_sta tree exceeds 16KB and
#        overflowed the heap ("corrupted top size"), aborting the steer before it
#        sent. Size the buffer to the subdoc buffer it is copied into.
# With both, a ClientSteer JSON drives a full BTM steer end to end -- verified:
# the client roams controller<->extender, both directions, repeatably.

# OneWifi reports client associations as per-event deltas and EasyMesh never
# reconciles, so a missed disassociation delta leaves a stale Associated=1 row
# forever -- inflating dashboard counts (one client "on" three BSSes) and making
# the controller reject steers whose source no longer matches the stale row.
# Enforce the single-association invariant at store time: a fresh Associated=1
# record for a STA deletes every other attribution of that STA (map + DB).

# The ieee1905 forking units can report started while their Unix socket paths are stale
# or not yet accepting. Both EasyMesh binaries let the resulting AlServiceException
# escape from startup, producing SIGABRT/core dumps. Retry the existing registration
# transaction for a bounded interval and fail startup normally if it never succeeds.

# Gate B (review P1/P2 #4): patch 0003 stops the controller's Topology-Query
# handler blocking on a disabled radio, but the agent still created a full
# onboarding em_t for every radio -- a disabled radio then sat permanently in
# em_state_agent_unconfigured with dev_init/WSC-M1 fanned out to it. This excludes
# a disabled radio at the source (em_orch_agent radio-insert loop skips create_node
# when radio_info.enabled is false); the radio stays represented in the data model
# but gets no state machine, so no M1 is generated. Generalises beyond 6 GHz.

# ---------------------------------------------------------------------------
# EasyMesh web UI (onewifi_em_cli, port 8888).
#
# The stock unified-wifi-mesh-cli recipe never lands in this image -- its
# do_fetch_mod ('go get -a' under the old go-native) fails, so /usr/bin/
# onewifi_em_cli is absent and em_cli.service loops on start-limit-hit. Ship a
# prebuilt binary cross-compiled from THIS tree's src/rdkb-cli Go source (so it
# matches the patched libemcli ABI and serves the same "EasyMesh R6" UI as the
# reference hardware). The ordered source patches, cross-build inputs, expected
# target format, and final binary hash are recorded in
# doc/easymesh/rev130-bringup-summary.md#rebuilding-the-precompiled-webui-helper.
#
# The binary reads /nvram/static and /nvram/remoteCtrl.json. A same-node image
# redeploy deliberately preserves /nvram, so the service drop-in refreshes the
# packaged assets in /usr/ccsp/EasyMesh/static on every start. Without that
# overwrite, a controller upgrade keeps serving the previous image's WebUI.
# em_cli is the controller-side web UI and links libemcli.so, which is only built
# and packaged in the broadband (controller) configuration of this recipe -- the
# extender build produces no libemcli, so shipping the prebuilt onewifi_em_cli there
# leaves a binary with an unsatisfiable NEEDED libemcli.so.0 and fails do_package_qa
# (file-rdeps). The extender does not run em_cli anyway. Ship it for the controller
# machine only, via qemux86bpibroadband overrides. (The stock em_cli.service is not
# installed on the extender either, so this leaves the extender image em_cli-free.)
#
# Prebuilt Go binary: it is already stripped, and Go binaries trip the ldflags/
# textrel/arch QA heuristics. Skip those for this package only.
INSANE_SKIP_${PN}_append_qemux86bpibroadband = " already-stripped ldflags textrel arch"
SRC_URI_append_qemux86bpibroadband = " file://em-cli.tar.gz file://em_cli-nvram.conf file://steer_drv.c file://steer.sh file://iot-device.svg"

# steer_drv: shell-side driver for commanded EasyMesh client steering. onewifi_em_cli
# (the web UI) exposes no steer route, and the interactive TUI is not installed, so a
# tiny C driver linking libemcli.so is the only way to submit a ClientSteer payload
# from a script: set_remote_addr(127.0.0.1,49153) -> get_network_tree_by_file(json) ->
# exec("steer_sta OneWifiMesh", node). Built from source here (not prebuilt) so it
# tracks the patched libemcli ABI automatically. Controller-only: libemcli.so is
# packaged only in the broadband config. Usage + JSON schema in
# doc/easymesh/container-hwsim-bringup-testing.md and demo/steering-demo.sh.
do_install_append_qemux86bpibroadband() {
    install -D -m 0755 ${WORKDIR}/onewifi_em_cli ${D}${bindir}/onewifi_em_cli
    install -d ${D}/usr/ccsp/EasyMesh/static
    cp -rf ${WORKDIR}/static/. ${D}/usr/ccsp/EasyMesh/static/
    # The helper archive supplies the cross-built Go binary and its baseline
    # assets.  Overlay the static files from the patched source tree so WebUI
    # fixes remain normal, reviewable source patches instead of binary tarball
    # replacements.
    install -m 0644 ${S}/src/rdkb-cli/static/index.html \
        ${S}/src/rdkb-cli/static/script.js \
        ${S}/src/rdkb-cli/static/style.css \
        ${D}/usr/ccsp/EasyMesh/static/
    install -m 0644 ${WORKDIR}/iot-device.svg \
        ${D}/usr/ccsp/EasyMesh/static/icons/iot-device.svg
    install -D -m 0644 ${WORKDIR}/em_cli-nvram.conf \
        ${D}${systemd_unitdir}/system/em_cli.service.d/nvram.conf

    # Compile against the just-installed libemcli.so (${D}${libdir}); rpath-link the
    # staging libdirs so libemcli's own NEEDED deps resolve at link time.
    ${CC} ${CFLAGS} ${WORKDIR}/steer_drv.c -o ${WORKDIR}/steer_drv \
        ${LDFLAGS} -L${D}${libdir} -lemcli \
        -Wl,-rpath-link,${D}${libdir} \
        -Wl,-rpath-link,${STAGING_LIBDIR} \
        -Wl,-rpath-link,${STAGING_DIR_TARGET}${libdir}
    install -D -m 0755 ${WORKDIR}/steer_drv ${D}${bindir}/steer_drv

    # Ergonomic wrapper: steer.sh <STA> <TARGET_BSSID> resolves the source device
    # from the OneWifiMesh DB and calls steer_drv. Pure shell, controller-only.
    install -D -m 0755 ${WORKDIR}/steer.sh ${D}${bindir}/steer.sh

    # The WebUI is another foreground process hidden behind a backgrounding
    # shell in the stock unit.  Make systemd own it directly so P0 can account
    # for its PID/RSS and so its output cannot grow an unbounded tmpfs file.
    u="${D}${systemd_unitdir}/system/em_cli.service"
    if [ -f "$u" ]; then
        if grep -q '^ExecStart=.*onewifi_em_cli.*em_cli\.log' "$u"; then
            sed -i 's|^ExecStart=.*onewifi_em_cli.*$|ExecStart=/usr/bin/onewifi_em_cli|' "$u"
        elif ! grep -q '^ExecStart=/usr/bin/onewifi_em_cli$' "$u"; then
            bbfatal "meta-cmf-bananapi-vcpe: unexpected em_cli.service ExecStart"
        fi

        sed -i 's/^Type=forking$/Type=simple/' "$u"
        sed -i '/^StandardOutput=/d; /^StandardError=/d; /^SyslogIdentifier=/d; /^LogRateLimitIntervalSec=/d; /^LogRateLimitBurst=/d' "$u"
        sed -i '/^ExecStart=\/usr\/bin\/onewifi_em_cli$/a StandardOutput=journal\
StandardError=journal\
SyslogIdentifier=onewifi_em_cli\
LogRateLimitIntervalSec=30s\
LogRateLimitBurst=500' "$u"
        grep -q '^RestartSec=' "$u" || sed -i '/^Restart=always/a RestartSec=3' "$u"

        grep -q '^Type=simple$' "$u" || bbfatal "meta-cmf-bananapi-vcpe: failed to make em_cli foreground"
        ! grep -q '/tmp/em_cli\.log' "$u" || bbfatal "meta-cmf-bananapi-vcpe: unbounded em_cli log remains"
        bbnote "meta-cmf-bananapi-vcpe: em_cli is foregrounded and uses bounded journald"
    fi
}

FILES_${PN}_append_qemux86bpibroadband = " ${bindir}/onewifi_em_cli ${bindir}/steer_drv ${bindir}/steer.sh /usr/ccsp/EasyMesh/static ${systemd_unitdir}/system/em_cli.service.d/nvram.conf "
