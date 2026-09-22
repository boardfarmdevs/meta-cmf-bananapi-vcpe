package main

import (
	"net"
	"strings"
)

func isInventoryAP(bssid, ssid string, vapMode int, modeKnown bool) bool {
	address, err := net.ParseMAC(bssid)
	return err == nil && len(address) == 6 && address[0]&1 == 0 &&
		address.String() != "00:00:00:00:00:00" && strings.TrimSpace(ssid) != "" &&
		modeKnown && vapMode == 0
}
