do_vcpe_fix_devices_rpi() {
    mkdir -p ${S}/devices_rpi/source/wifi
    if [ ! -f ${S}/devices_rpi/source/wifi/wifi_hal.c ]; then
        yes "" | head -n 6000 > ${S}/devices_rpi/source/wifi/wifi_hal.c
    fi
}
addtask vcpe_fix_devices_rpi after do_unpack before do_configure
