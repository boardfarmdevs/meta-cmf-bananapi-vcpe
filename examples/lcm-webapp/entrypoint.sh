#!/bin/sh
# PID-1 wrapper: produces periodic stdout heartbeat (which cthulhu's
# container-up watchdog appears to need to see) while keeping lighttpd
# alive in the background.  Forwards SIGTERM/SIGINT so a clean shutdown
# from cthulhu kills both.

trap 'echo "[entrypoint] shutdown requested"; kill -TERM $LIGHTTPD_PID 2>/dev/null; wait $LIGHTTPD_PID; exit 0' TERM INT

/usr/sbin/lighttpd -D -f /etc/lighttpd/lighttpd.conf &
LIGHTTPD_PID=$!
echo "[entrypoint] lighttpd started pid=$LIGHTTPD_PID, serving on :8888"

i=0
while kill -0 $LIGHTTPD_PID 2>/dev/null; do
    i=$((i+1))
    echo "[entrypoint] alive #$i pid1=$$ lighttpd=$LIGHTTPD_PID host=$(hostname) uname=$(uname -srm)"
    sleep 5
done

echo "[entrypoint] lighttpd exited unexpectedly"
exit 1
