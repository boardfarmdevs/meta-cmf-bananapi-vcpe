package main

import (
	"fmt"
	"net/http"
	"testing"
)

func TestSetSSIDReplyCarriesTheControllersStatus(t *testing.T) {
	for _, c := range []struct {
		status  string
		err     error
		code    int
		success bool
	}{
		{"Success", nil, http.StatusOK, true},
		{"Error_No_Config_Change_Detected", nil, http.StatusOK, true},
		{"Error_Prev_Cmd_In_Progress", nil, http.StatusConflict, false},
		{"Error_Invalid_Input", nil, http.StatusUnprocessableEntity, false},
		{"Error_Not_Ready", nil, http.StatusServiceUnavailable, false},
		{"Error_Other", nil, http.StatusBadGateway, false},
		{"", fmt.Errorf("set_ssid command execution failed"), http.StatusBadGateway, false},
	} {
		code, reply := setSSIDReply(c.status, c.err)
		if code != c.code || reply["success"] != c.success {
			t.Errorf("%q %v: %d %v, want %d %v", c.status, c.err, code, reply["success"], c.code, c.success)
		}
	}
}
