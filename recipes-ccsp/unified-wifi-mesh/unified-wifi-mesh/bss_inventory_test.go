package main

import "testing"

func TestInventoryAP(t *testing.T) {
	for _, test := range []struct {
		name, bssid, ssid string
		mode              int
		known, want       bool
	}{
		{"backhaul AP", "02:00:00:00:01:01", "mesh_backhaul", 0, true, true},
		{"private AP", "02:00:00:00:01:02", "private_ssid", 0, true, true},
		{"iot AP", "02:00:00:00:01:03", "iot_ssid", 0, true, true},
		{"backhaul STA", "02:00:00:00:01:01", "mesh_backhaul", 1, true, false},
		{"unknown mode", "02:00:00:00:01:01", "mesh_backhaul", 0, false, false},
		{"invalid mode", "02:00:00:00:01:01", "mesh_backhaul", -1, true, false},
		{"zero", "00:00:00:00:00:00", "mesh_backhaul", 0, true, false},
		{"multicast", "01:00:00:00:01:01", "mesh_backhaul", 0, true, false},
		{"malformed", "not-a-mac", "mesh_backhaul", 0, true, false},
		{"empty SSID", "02:00:00:00:01:01", "", 0, true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if got := isInventoryAP(test.bssid, test.ssid, test.mode, test.known); got != test.want {
				t.Fatalf("isInventoryAP = %t, want %t", got, test.want)
			}
		})
	}
}
