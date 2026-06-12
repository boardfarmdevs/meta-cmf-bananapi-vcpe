SUMMARY  = "Tic-Tac-Toe static web app content + lighttpd config"
DESCRIPTION = "Installs the tic-tac-toe HTML/JS/CSS to /www/pages and a \
matching lighttpd.conf to /etc."
LICENSE  = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://index.html \
    file://style.css \
    file://script.js \
    file://lighttpd.conf \
"

S = "${WORKDIR}"

# Note: lighttpd's own ipk installs /www/pages/index.html, so we use /srv/tictactoe
# instead to avoid the opkg file-conflict.
do_install() {
    install -d ${D}/srv/tictactoe
    install -m 0644 ${WORKDIR}/index.html ${D}/srv/tictactoe/index.html
    install -m 0644 ${WORKDIR}/style.css  ${D}/srv/tictactoe/style.css
    install -m 0644 ${WORKDIR}/script.js  ${D}/srv/tictactoe/script.js

    install -m 0644 ${WORKDIR}/lighttpd.conf ${D}/srv/tictactoe/lighttpd.conf
}

FILES:${PN} = " \
    /srv/tictactoe/index.html \
    /srv/tictactoe/style.css \
    /srv/tictactoe/script.js \
    /srv/tictactoe/lighttpd.conf \
"
