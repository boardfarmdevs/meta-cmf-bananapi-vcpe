# Tiny i386 webapp packaged as an OCI image, intended to be deployed to an
# RDK-B vCPE LXC running the LCM stack (cthulhu+crun via celephais).
#
# Built/pushed by build-and-push.sh, pulled+converted to a bundle by
# ../from-registry/from-registry.sh, then deployed via
# ba-cli "Device.SoftwareModules.InstallDU(URL=...)".

FROM i386/alpine:3.18

RUN apk add --no-cache lighttpd && \
    rm -rf /var/www/localhost /etc/lighttpd/mod_*.conf 2>/dev/null || true && \
    mkdir -p /var/www/htdocs

COPY www/             /var/www/htdocs/
COPY lighttpd.conf    /etc/lighttpd/lighttpd.conf
COPY entrypoint.sh    /entrypoint.sh
RUN chmod +x /entrypoint.sh

# cthulhu's container-up watchdog wants periodic stdout from PID 1.
# entrypoint.sh runs lighttpd in the background, emits a heartbeat every 5s,
# and forwards signals so cthulhu's stop is clean.
ENTRYPOINT ["/entrypoint.sh"]
