package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
)

// POST /api/v1/renew asks the controller to renew radios: an Autoconfig Renew to each, its
// agent then running WSC again for it (M1/M2) and reapplying the controller's configuration.
// Each radio is named by its agent's AL MAC and its current operating class:
//
//	{"devices": [{"al_mac": "00:60:2f:da:68:e4", "classes": [115]}]}
//
// The request goes to the controller as a wfa-dataelements:Renew subdoc (CfgRenew.json's form,
// series 0258), which the controller checks as a whole: an agent it does not know, or a class
// that names no radio of it (or two), refuses the request and nothing is renewed.
//
// Answers: 202 with the radios requested; 400 for a request that is not well formed here; 422
// when the controller refuses it (Error_Invalid_Input); 503 when it is not ready; 502 for any
// other answer.

type renewDevice struct {
	ALMac   string `json:"al_mac"`
	Classes []int  `json:"classes"`
}

type renewRequest struct {
	Devices []renewDevice `json:"devices"`
}

var renewMACPattern = regexp.MustCompile(`^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$`)

// renewSubmit sends the subdoc to the controller and returns its status ("Success", ...);
// submitRenewSubdoc (main.go, through libemcli) outside the tests.
var renewSubmit = submitRenewSubdoc

// renewSubdoc checks a request and returns its wfa-dataelements:Renew subdoc and the number of
// radios it names.
func renewSubdoc(request renewRequest) ([]byte, int, error) {
	if len(request.Devices) == 0 {
		return nil, 0, fmt.Errorf("no devices")
	}
	type class struct {
		Class int `json:"Class"`
	}
	type radio struct {
		CurrentOperatingClasses []class `json:"CurrentOperatingClasses"`
	}
	type device struct {
		ID        string  `json:"ID"`
		RadioList []radio `json:"RadioList"`
	}
	devices := make([]device, 0, len(request.Devices))
	radios := 0
	for _, requested := range request.Devices {
		mac := strings.ToLower(requested.ALMac)
		if !renewMACPattern.MatchString(mac) || mac == "00:00:00:00:00:00" {
			return nil, 0, fmt.Errorf("al_mac %q is not a MAC address", requested.ALMac)
		}
		if len(requested.Classes) == 0 {
			return nil, 0, fmt.Errorf("al_mac %s: no classes", mac)
		}
		entry := device{ID: mac}
		for _, c := range requested.Classes {
			if c < 1 || c > 255 {
				return nil, 0, fmt.Errorf("al_mac %s: class %d is not an operating class", mac, c)
			}
			entry.RadioList = append(entry.RadioList, radio{CurrentOperatingClasses: []class{{Class: c}}})
			radios++
		}
		devices = append(devices, entry)
	}
	subdoc, err := json.Marshal(map[string]interface{}{
		"wfa-dataelements:Renew": map[string]interface{}{
			"ID":              "OneWifiMesh",
			"NumberOfDevices": len(devices),
			"DeviceList":      devices,
		},
	})
	return subdoc, radios, err
}

func renewHandler(w http.ResponseWriter, r *http.Request) {
	var request renewRequest
	reply := func(status int, body map[string]interface{}) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(body)
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 64*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&request); err != nil {
		reply(http.StatusBadRequest, map[string]interface{}{"success": false, "message": "invalid request: " + err.Error()})
		return
	}
	subdoc, radios, err := renewSubdoc(request)
	if err != nil {
		reply(http.StatusBadRequest, map[string]interface{}{"success": false, "message": err.Error()})
		return
	}
	status, err := renewSubmit(subdoc)
	switch {
	case err != nil:
		reply(http.StatusBadGateway, map[string]interface{}{"success": false, "message": err.Error()})
	case status == "Success":
		reply(http.StatusAccepted, map[string]interface{}{"success": true, "radios": radios, "status": status})
	case status == "Error_Invalid_Input":
		reply(http.StatusUnprocessableEntity, map[string]interface{}{"success": false, "status": status,
			"message": "the controller refused the request (its log names the reason); nothing was renewed"})
	case status == "Error_Not_Ready":
		reply(http.StatusServiceUnavailable, map[string]interface{}{"success": false, "status": status})
	default:
		reply(http.StatusBadGateway, map[string]interface{}{"success": false, "status": status})
	}
}
