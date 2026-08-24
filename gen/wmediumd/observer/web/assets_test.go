package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestEmbeddedConsoleContainsPhase2ViewsAndTypedControls(t *testing.T) {
	html, err := fs.ReadFile(Assets, "index.html")
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"wmediumd Console", "Active link paths", "Radio / frequency counters", "VIF → radio mapping", "Event timeline", "Radio identities", "Set pair SNR", "Clear frequency override", "Undo last"} {
		if !strings.Contains(string(html), want) {
			t.Errorf("index.html missing %q", want)
		}
	}
	javascript, err := fs.ReadFile(Assets, "app.js")
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"/api/v1/controls/pairs/set", "/api/v1/controls/frequencies/set", "/api/v1/controls/frequencies/clear", "/api/v1/controls/undo", "X-Wmediumd-CSRF", "active_links", "radio_frequencies", "identity_inventory", "station.label"} {
		if !strings.Contains(string(javascript), want) {
			t.Errorf("app.js missing %q", want)
		}
	}
	if strings.Contains(string(javascript), "innerHTML") {
		t.Fatal("UI uses innerHTML with live protocol data")
	}
}
