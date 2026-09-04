#!/bin/sh
# steer.sh <STA_MAC> <TARGET_BSSID> [OP_CLASS] [CHANNEL] [gentle]
#
# Commanded EasyMesh client steering, the ergonomic form: given only the station
# and the destination BSSID, resolve the source device (AL-MAC / RUID / source
# BSSID) from the controller's data model, build the ClientSteer payload, and
# submit it via steer_drv. Runs on the controller (needs the OneWifiMesh DB and
# /usr/bin/steer_drv). Op class / channel default from the target's band and can
# be overridden with the optional 3rd/4th args.
#
# Example: steer.sh 02:00:00:00:03:00 02:00:00:51:38:4f

STA="$1"; TGT="$2"; OPCLASS="$3"; CHAN="$4"; MODE="$5"
if [ -z "$STA" ] || [ -z "$TGT" ]; then
    echo "usage: steer.sh <STA_MAC> <TARGET_BSSID> [op_class] [channel] [gentle]" >&2
    exit 2
fi

# Continuous reconciliation must not kick a station off its serving AP merely
# because it declines a candidate. Gentle mode keeps the mandate and abridged
# target list but leaves a rejecting station associated for a measured retry.
case "$MODE" in
    gentle)
        BTM_DISASSOC_IMMINENT=false
        BTM_DISASSOC_TIMER=0
        BTM_OPPORTUNITY_WINDOW=50
        ;;
    "")
        BTM_DISASSOC_IMMINENT=true
        BTM_DISASSOC_TIMER=5
        BTM_OPPORTUNITY_WINDOW=5
        ;;
    *)
        echo "steer.sh: fifth argument must be 'gentle' when supplied" >&2
        exit 2
        ;;
esac

MYSQL="mysql -N -ubpi -proot OneWifiMesh"

# Source: where the controller currently believes the STA is associated.
SRC_BSSID=$($MYSQL -e "select BSSID from STAList where MACAddress=\"$STA\" and Associated=1 limit 1;" 2>/dev/null)
if [ -z "$SRC_BSSID" ]; then
    echo "steer.sh: STA $STA is not associated in STAList (nothing to steer)" >&2
    exit 1
fi

# BSSList.ID = OneWifiMesh@<AL_MAC>@<RUID>@<BSSID>@<idx> -- carries the device+radio.
SRC_ID=$($MYSQL -e "select ID from BSSList where BSSID=\"$SRC_BSSID\" limit 1;" 2>/dev/null)
if [ -z "$SRC_ID" ]; then
    echo "steer.sh: source BSS $SRC_BSSID not found in BSSList" >&2
    exit 1
fi
AL_MAC=$(echo "$SRC_ID" | cut -d@ -f2)
RUID=$(echo "$SRC_ID" | cut -d@ -f3)

# Target must be a BSS the controller knows; its band picks sane op-class/channel
# defaults (0=2.4GHz, 1=5GHz, 3=6GHz) unless overridden on the command line.
TGT_BAND=$($MYSQL -e "select r.Band from BSSList b join RadioList r on b.RUID=r.RadioID where b.BSSID=\"$TGT\" limit 1;" 2>/dev/null)
if [ -z "$TGT_BAND" ]; then
    echo "steer.sh: target BSS $TGT is not known to the controller (BSSList)" >&2
    exit 1
fi
case "$TGT_BAND" in
    0) OPCLASS=${OPCLASS:-81};  CHAN=${CHAN:-6}  ;;
    1) OPCLASS=${OPCLASS:-115}; CHAN=${CHAN:-36} ;;
    3) OPCLASS=${OPCLASS:-131}; CHAN=${CHAN:-37} ;;
    *) OPCLASS=${OPCLASS:-115}; CHAN=${CHAN:-36} ;;
esac

# The source comes from the controller's model, which can lag reality (BTM-report
# loss / stale-assoc race). If it already equals the target the steer is a no-op --
# refuse rather than emit a bogus same-BSS request.
if [ "$SRC_BSSID" = "$TGT" ]; then
    echo "steer.sh: controller model already has $STA on $TGT (source==target); model may be stale -- refusing" >&2
    exit 1
fi

JSON="/tmp/steer-${STA}.json"
cat > "$JSON" <<EOF
{ "wfa-dataelements:ClientSteer": { "Network": { "ID": "OneWifiMesh",
  "DeviceList": [{ "ID": "$AL_MAC",
    "RadioList": [{ "ID": "$RUID",
      "BSSList": [{ "BSSID": "$SRC_BSSID",
        "STAList": [{ "MACAddress": "$STA", "Associated": true,
          "ClientSteer": {
            "TargetBSSID": "$TGT",
            "RequestMode": { "Steering_Mandate": 1 },
            "BTMDisassociationImminent": $BTM_DISASSOC_IMMINENT,
            "BTMAbridged": true,
            "LinkRemovalImminent": false,
            "SteeringOpportunityWindow": $BTM_OPPORTUNITY_WINDOW,
            "BTMDisassociationTimer": $BTM_DISASSOC_TIMER,
            "TargetBSSOperatingClass": $OPCLASS,
            "TargetBSSChannel": $CHAN
          } }] }] }] }] } } }
EOF

echo "steer.sh: $STA  $SRC_BSSID (dev $AL_MAC) -> $TGT  [band $TGT_BAND opclass $OPCLASS ch $CHAN]"
exec /usr/bin/steer_drv "steer_sta OneWifiMesh" "$JSON"
