package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRenewSubdocIsCfgRenewForm(t *testing.T) {
	subdoc, radios, err := renewSubdoc(renewRequest{Devices: []renewDevice{
		{ALMac: "00:60:2F:DA:68:E4", Classes: []int{115, 81}},
		{ALMac: "02:00:00:00:69:20", Classes: []int{131}},
	}})
	if err != nil || radios != 3 {
		t.Fatalf("renewSubdoc: %d radios, %v", radios, err)
	}
	var parsed struct {
		Renew struct {
			NumberOfDevices int
			DeviceList      []struct {
				ID        string
				RadioList []struct {
					CurrentOperatingClasses []struct{ Class int }
				}
			}
		} `json:"wfa-dataelements:Renew"`
	}
	if err := json.Unmarshal(subdoc, &parsed); err != nil {
		t.Fatal(err)
	}
	devices := parsed.Renew.DeviceList
	if parsed.Renew.NumberOfDevices != 2 || len(devices) != 2 || devices[0].ID != "00:60:2f:da:68:e4" ||
		len(devices[0].RadioList) != 2 || devices[0].RadioList[1].CurrentOperatingClasses[0].Class != 81 ||
		devices[1].RadioList[0].CurrentOperatingClasses[0].Class != 131 {
		t.Fatalf("subdoc %s", subdoc)
	}
}

func TestRenewSubdocRefusesWhatNamesNoRadio(t *testing.T) {
	for _, request := range []renewRequest{
		{},
		{Devices: []renewDevice{{ALMac: "00:60:2f:da:68", Classes: []int{115}}}},
		{Devices: []renewDevice{{ALMac: "CfgRenew.json", Classes: []int{115}}}},
		{Devices: []renewDevice{{ALMac: "00:00:00:00:00:00", Classes: []int{115}}}},
		{Devices: []renewDevice{{ALMac: "00:60:2f:da:68:e4"}}},
		{Devices: []renewDevice{{ALMac: "00:60:2f:da:68:e4", Classes: []int{0}}}},
		{Devices: []renewDevice{{ALMac: "00:60:2f:da:68:e4", Classes: []int{256}}}},
	} {
		if _, _, err := renewSubdoc(request); err == nil {
			t.Errorf("accepted %+v", request)
		}
	}
}

func TestRenewHandlerAnswersWithTheControllersStatus(t *testing.T) {
	saved := renewSubmit
	defer func() { renewSubmit = saved }()
	for _, c := range []struct {
		status string
		err    error
		code   int
	}{
		{"Success", nil, http.StatusAccepted},
		{"Error_Invalid_Input", nil, http.StatusUnprocessableEntity},
		{"Error_Not_Ready", nil, http.StatusServiceUnavailable},
		{"Error_Other", nil, http.StatusBadGateway},
		{"", fmt.Errorf("renew command execution failed"), http.StatusBadGateway},
	} {
		submitted := 0
		renewSubmit = func(subdoc []byte) (string, error) {
			submitted++
			return c.status, c.err
		}
		recorder := httptest.NewRecorder()
		renewHandler(recorder, httptest.NewRequest(http.MethodPost, "/api/v1/renew",
			strings.NewReader(`{"devices": [{"al_mac": "00:60:2f:da:68:e4", "classes": [115]}]}`)))
		if recorder.Code != c.code || submitted != 1 {
			t.Errorf("%q: %d (submitted %d), want %d", c.status, recorder.Code, submitted, c.code)
		}
	}
}

func TestRenewHandlerRefusesBeforeTheController(t *testing.T) {
	saved := renewSubmit
	defer func() { renewSubmit = saved }()
	renewSubmit = func(subdoc []byte) (string, error) {
		t.Fatalf("submitted %s", subdoc)
		return "", nil
	}
	for _, body := range []string{
		`not json`,
		`{"devices": [{"al_mac": "00:60:2f:da:68:e4", "classes": [115]}], "extra": 1}`,
		`{"devices": [{"al_mac": "00:60:2f:da:68:e4", "classes": [300]}]}`,
		`{"devices": []}`,
	} {
		recorder := httptest.NewRecorder()
		renewHandler(recorder, httptest.NewRequest(http.MethodPost, "/api/v1/renew", strings.NewReader(body)))
		if recorder.Code != http.StatusBadRequest {
			t.Errorf("%s: %d", body, recorder.Code)
		}
	}
}
