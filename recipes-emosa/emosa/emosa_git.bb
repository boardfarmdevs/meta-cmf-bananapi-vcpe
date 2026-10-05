SUMMARY = "EMOSA: OpenSync pods as EasyMesh agents (the adapter in C)"
DESCRIPTION = "EMOSA's agent, fleet and GRE termination point in C (emosa-lab, c/): each \
OpenSync pod handed to the fleet's front port appears at the gateway's EasyMesh controller \
as an agent of its own. An image installs it only when asked (EMOSA_ADAPTER, \
rdk-generic-broadband-image.bbappend; easymesh-labs plan 5.5)."
HOMEPAGE = "https://vcpe.dev/emosa-lab/"
SECTION = "net"

# emosa-lab's LICENSE (the Apache License 2.0); its bill of materials is in the package
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://../LICENSE;md5=3b83ef96387f14655fc854ddc3c6bd57"

# The emosa-lab commit, the one gen/vm/lxd/emosa-lab.env pins for the lab's EMOSA option:
# the image and the lab deploy the same adapter.
def emosa_lab_commit(d):
    import os
    import re
    env = os.path.join(os.path.dirname(d.getVar('FILE')), '..', '..', 'gen', 'vm', 'lxd', 'emosa-lab.env')
    bb.parse.mark_dependency(d, env)
    with open(env) as f:
        found = re.search(r'^EMOSA_LAB_COMMIT=([0-9a-f]{40})$', f.read(), re.MULTILINE)
    if not found:
        bb.fatal('%s: no EMOSA_LAB_COMMIT' % env)
    return found.group(1)

SRC_URI = "git://github.com/boardfarmdevs/emosa-lab.git;protocol=https;branch=main"
SRCREV = "${@emosa_lab_commit(d)}"
# the release of emosa-lab's pyproject.toml at that commit
PV = "0.1.0+git${SRCPV}"
S = "${WORKDIR}/git/c"

inherit cmake pkgconfig systemd python3native

DEPENDS = "cjson openssl sqlite3 rdk-logger"

# c/README.md "Logging, version and package": logging through RDK's logger into
# /rdklogs/logs, the package's layout, the units, the bill of materials; EMOSA's
# configuration and state on the gateway's persistent /nvram, which an image upgrade keeps,
# and its agents' status (rewritten once a second) in RAM, /run; the agents' interfaces in a
# network namespace of their own, emosa: the gateway's em_ctrl took an agent whose AL MAC
# was on one of its own interfaces for its co-located agent (emosa-lab spec 2.1)
EXTRA_OECMAKE = " \
    -DEMOSA_INSTALL_DATA=ON \
    -DEMOSA_RDK_LOGGER=ON \
    -DEMOSA_REVISION=${@d.getVar('SRCREV')[:12]} \
    -DEMOSA_SCHEMAS_DIR=${datadir}/emosa/schemas \
    -DEMOSA_PROFILES_DIR=${datadir}/emosa/profiles \
    -DEMOSA_SYSTEMD_UNIT_DIR=${systemd_system_unitdir} \
    -DEMOSA_DNSMASQ=${bindir}/dnsmasq \
    -DEMOSA_FLEET_CONFIG=/nvram/emosa/fleet-config.json \
    -DEMOSA_AGENT_CONFIG_DIR=/nvram/emosa/agents \
    -DEMOSA_GTP_CONFIG=/nvram/emosa/gtp-config.json \
    -DEMOSA_STATE_ROOT=/nvram/emosa/state \
    -DEMOSA_RUN_ROOT=/run/emosa \
    -DEMOSA_NETNS=emosa \
"

# the GRE termination point a package of its own: the gateway serves the pods' onboarding
# and ends their GRE (plan 5.2, decided 4 Oct); an image may still leave it out (EMOSA_GTP)
PACKAGES =+ "${PN}-gtp"
FILES:${PN}-gtp = " \
    ${bindir}/emosa-gtp-c \
    ${systemd_system_unitdir}/emosa-gtp.service \
    ${datadir}/emosa/gtp.example.json \
"
FILES:${PN} += " \
    ${systemd_system_unitdir}/emosa-agent@.service \
    ${libexecdir}/emosa \
    ${datadir}/emosa \
"
CONFFILES:${PN} = "${sysconfdir}/default/emosa"

SYSTEMD_PACKAGES = "${PN} ${PN}-gtp"
# the fleet is inert until /etc/emosa-fleet.json exists, it enables an agent per pod; the
# GTP is inert until /etc/emosa-gtp.json exists
SYSTEMD_SERVICE:${PN} = "emosa-fleet.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"
SYSTEMD_SERVICE:${PN}-gtp = "emosa-gtp.service"
SYSTEMD_AUTO_ENABLE:${PN}-gtp = "enable"

# the agent's link helper: bash, iproute2's ip (a macvlan per agent, the agents' namespace)
RDEPENDS:${PN} = "bash iproute2"
RDEPENDS:${PN}-gtp = "${PN} dnsmasq iproute2"
