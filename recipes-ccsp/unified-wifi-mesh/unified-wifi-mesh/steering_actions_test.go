package main

import (
	"testing"
	"time"
)

func TestSteeringActionHistoryIsBoundedAndFresh(test *testing.T) {
	steeringActions.Lock()
	steeringActions.items = nil
	steeringActions.Unlock()
	now := time.Now()
	for index := 0; index < 110; index++ {
		recordBTMRequest("station", "source", "target", now)
	}
	actions := currentSteeringActions(now)
	if len(actions) != 100 || actions[0].Method != "btm-request" {
		test.Fatal(actions)
	}
	actions[0].Source = "mutated"
	if currentSteeringActions(now)[0].Source != "source" {
		test.Fatal("history alias")
	}
	if len(currentSteeringActions(now.Add(31*time.Second))) != 0 {
		test.Fatal("expired requests survived")
	}
}

func TestNonBTMReportsAreExplicitAndValidated(test *testing.T) {
	now := time.Now()
	if recordNonBTMReport("bad", "bad", "bad", now) == nil {
		test.Fatal("invalid report accepted")
	}
	if err := recordNonBTMReport("02:00:00:00:00:01", "02:00:00:00:00:02", "02:00:00:00:00:03", now); err != nil {
		test.Fatal(err)
	}
	actions := currentSteeringActions(now)
	last := actions[len(actions)-1]
	if last.Method != "non-btm" || last.Evidence != "operator-report" {
		test.Fatal(last)
	}
}
