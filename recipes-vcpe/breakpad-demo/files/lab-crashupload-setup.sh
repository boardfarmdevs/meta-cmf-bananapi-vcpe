#!/bin/sh
# Lab crash-upload setup (dev/lab images only), installed via the breakpad-demo
# recipe and run once at boot.
#
# Makes the stock RDK-B crash pipeline deliver minidumps to the per-desk lab SSR
# instead of the production crash portal:
#   1. override exec_curl_mtls with a plain-curl version (no Xpki mTLS),
#   2. point CrashUpload.S3SigningUrl at the lab SSR (.35 on this CPE's WAN
#      subnet - computed at runtime because it differs per desk),
#   3. disable cloud-upload encryption (the lab SSR stores plain dumps).
#
# After this runs, a crash -> /minidumps/*.dmp is uploaded by the stock systemd
# coredump-upload.path -> uploadDumps.sh trigger, no test-side stubbing needed.
#
# systemd ordering at boot is unreliable here, so the script waits for the bits
# it needs (log dir, erouter0 IP) rather than depending on a target.

LAB_DIR=/usr/share/lab-crashupload
mkdir -p /rdklogs/logs 2>/dev/null
LOG=/rdklogs/logs/lab-crashupload.log

log() {
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') lab-crashupload: $*" >> "$LOG" 2>/dev/null
}

# 1. plain-curl exec_curl_mtls override (no deps; scripts source
#    $RDK_PATH/exec_curl_mtls.sh, overriding their inline mTLS version).
if [ -f "$LAB_DIR/exec_curl_mtls.sh" ]; then
    cp "$LAB_DIR/exec_curl_mtls.sh" /lib/rdk/exec_curl_mtls.sh 2>/dev/null \
        && log "installed plain-curl exec_curl_mtls.sh"
fi

# 2. SSR is at .35 on this CPE's WAN (erouter0) subnet. Wait for the WAN IP
#    (also a good proxy for CCSP/dmcli being ready), up to ~120s.
subnet=""
i=0
while [ "$i" -lt 60 ]; do
    subnet=$(ip -4 addr show erouter0 2>/dev/null \
        | awk '/inet /{print $2}' | head -n1 | cut -d/ -f1 | cut -d. -f1-3)
    [ -n "$subnet" ] && break
    i=$((i + 1))
    sleep 2
done
if [ -n "$subnet" ]; then
    url="https://${subnet}.35:8443/cgi-bin/rdkb.cgi"
    dmcli eRT setv \
        Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.CrashUpload.S3SigningUrl \
        string "$url" >/dev/null 2>&1
    log "set CrashUpload.S3SigningUrl=$url"
else
    log "WARN: no erouter0 IPv4 after wait; CrashUpload.S3SigningUrl not set"
fi

# 3. Disable cloud-upload encryption (best effort; the default when unset is
#    already 'no encryption', so a not-yet-ready syscfg here is harmless).
i=0
while [ "$i" -lt 15 ]; do
    syscfg get encryptcloudupload >/dev/null 2>&1 && break
    i=$((i + 1))
    sleep 2
done
if syscfg set encryptcloudupload false >/dev/null 2>&1; then
    syscfg commit >/dev/null 2>&1
    log "disabled encryptcloudupload"
else
    log "note: syscfg not ready; relying on default (encryption off)"
fi

exit 0
