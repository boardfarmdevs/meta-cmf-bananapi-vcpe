package main

import (
	"fmt"
	"net"
	"sync"
	"time"
)

type steeringAction struct {
	Station     string    `json:"sta_mac"`
	Source      string    `json:"source_bssid"`
	Target      string    `json:"target_bssid"`
	Method      string    `json:"method"`
	RequestedAt time.Time `json:"requested_at"`
	Evidence    string    `json:"evidence"`
}

var steeringActions = struct {
	sync.Mutex
	items []steeringAction
}{}

func recordBTMRequest(station, source, target string, started time.Time) {
	steeringActions.Lock()
	defer steeringActions.Unlock()
	steeringActions.items = append(steeringActions.items, steeringAction{station, source, target, "btm-request", started.UTC(), "native-acceptance"})
	if len(steeringActions.items) > 100 {
		steeringActions.items = steeringActions.items[len(steeringActions.items)-100:]
	}
}

func recordNonBTMReport(station, source, target string, now time.Time) error {
	addresses := []*string{&station, &source, &target}
	for _, value := range addresses {
		address, err := net.ParseMAC(*value)
		if err != nil || len(address) != 6 {
			return fmt.Errorf("non-BTM reports require station, source and target six-byte MAC addresses")
		}
		*value = address.String()
	}
	if source == target {
		return fmt.Errorf("non-BTM report source and target must differ")
	}
	steeringActions.Lock()
	defer steeringActions.Unlock()
	steeringActions.items = append(steeringActions.items, steeringAction{station, source, target, "non-btm", now.UTC(), "operator-report"})
	if len(steeringActions.items) > 100 {
		steeringActions.items = steeringActions.items[len(steeringActions.items)-100:]
	}
	return nil
}

func currentSteeringActions(now time.Time) []steeringAction {
	steeringActions.Lock()
	defer steeringActions.Unlock()
	result := []steeringAction{}
	for _, action := range steeringActions.items {
		if age := now.Sub(action.RequestedAt); age >= 0 && age < 30*time.Second {
			result = append(result, action)
		}
	}
	return result
}
