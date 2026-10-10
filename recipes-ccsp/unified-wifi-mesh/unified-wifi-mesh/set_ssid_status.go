package main

import "net/http"

// The controller's answer to a set_ssid (series 0263). The profiles route answered success
// whatever the controller said, so an SSID change it refused, or one it did not carry out
// while another was in flight, looked applied (rdk-1010, 10 October: the network left on a
// lab SSID after its restore "succeeded").
func setSSIDReply(status string, err error) (int, map[string]interface{}) {
	switch {
	case err != nil:
		return http.StatusBadGateway, map[string]interface{}{"success": false, "message": err.Error()}
	case status == "Success":
		return http.StatusOK, map[string]interface{}{"success": true, "status": status,
			"message": "Profile updated successfully"}
	case status == "Error_No_Config_Change_Detected":
		return http.StatusOK, map[string]interface{}{"success": true, "status": status,
			"message": "no change: the network already has this configuration"}
	case status == "Error_Prev_Cmd_In_Progress":
		return http.StatusConflict, map[string]interface{}{"success": false, "status": status,
			"message": "another SSID change or a radio's configuration is in progress: nothing changed, try again"}
	case status == "Error_Invalid_Input":
		return http.StatusUnprocessableEntity, map[string]interface{}{"success": false, "status": status,
			"message": "the controller refused the configuration"}
	case status == "Error_Not_Ready":
		return http.StatusServiceUnavailable, map[string]interface{}{"success": false, "status": status}
	default:
		return http.StatusBadGateway, map[string]interface{}{"success": false, "status": status}
	}
}
