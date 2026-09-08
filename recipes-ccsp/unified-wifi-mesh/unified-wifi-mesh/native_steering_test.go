package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const validSteeringBody = `{"station":"02:00:00:00:03:00","source_bssid":"02:00:00:aa:aa:01","target_bssid":"02:00:00:aa:aa:02","operating_class":115,"channel":36}`

func TestNativeSteeringRequiresUnambiguousNativeAcceptance(test *testing.T) {
	for _, stdout := range []string{"steer_drv_status=Success\n", "steer_drv_status=Error_Prev_Cmd_In_Progress\n", "", "steer_drv_status=Success\nsteer_drv_status=Success\n"} {
		handler := makeNativeSteeringHandler(func(ctx context.Context, arguments []string) (string, string, int) {
			if len(arguments) != 6 || arguments[4] != "gentle" || arguments[5] != "02:00:00:aa:aa:01" {
				test.Fatal(arguments)
			}
			return stdout, "", 0
		})
		response := httptest.NewRecorder()
		handler(response, httptest.NewRequest("POST", "/api/v1/steer-native", strings.NewReader(validSteeringBody)))
		var body map[string]interface{}
		if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
			test.Fatal(err)
		}
		want := stdout == "steer_drv_status=Success\n"
		if body["success"] != want || (response.Code == http.StatusOK) != want {
			test.Fatal(response.Body.String())
		}
	}
}

func TestNativeSteeringRejectsInvalidInputsBeforeExecuting(test *testing.T) {
	for _, body := range []string{validSteeringBody + "{}", strings.Replace(validSteeringBody, "115", "999", 1),
		strings.Replace(validSteeringBody, ":aa:02", ":aa:01", 1),
		strings.Replace(validSteeringBody, "02:00:00:00:03:00", "02:00:00:00:00:00:03:00", 1),
		strings.Replace(validSteeringBody, "36", "37", 1),
		strings.Replace(validSteeringBody, "station", "command", 1), strings.Repeat(" ", 5000) + validSteeringBody} {
		handler := makeNativeSteeringHandler(func(context.Context, []string) (string, string, int) {
			test.Fatal("invalid request executed")
			return "", "", 0
		})
		response := httptest.NewRecorder()
		handler(response, httptest.NewRequest("POST", "/api/v1/steer-native", strings.NewReader(body)))
		if response.Code != http.StatusBadRequest {
			test.Fatal(response.Code, body)
		}
	}
}

func TestNativeSteeringDoesNotQueueOrOwnPassiveNativeLock(test *testing.T) {
	started, release, done := make(chan struct{}), make(chan struct{}), make(chan struct{})
	handler := makeNativeSteeringHandler(func(context.Context, []string) (string, string, int) {
		close(started)
		<-release
		return "steer_drv_status=Success", "", 0
	})
	go func() {
		defer close(done)
		handler(httptest.NewRecorder(), httptest.NewRequest("POST", "/api/v1/steer-native", strings.NewReader(validSteeringBody)))
	}()
	defer func() { close(release); <-done }()
	select {
	case <-started:
	case <-time.After(time.Second):
		test.Fatal("submission did not start")
	}
	passive := make(chan struct{})
	go func() { apiRequestMutex.Lock(); apiRequestMutex.Unlock(); close(passive) }()
	select {
	case <-passive:
	case <-time.After(time.Second):
		test.Fatal("steering holds passive native lock")
	}
	response := httptest.NewRecorder()
	handler(response, httptest.NewRequest("POST", "/api/v1/steer-native", strings.NewReader(validSteeringBody)))
	if response.Code != http.StatusTooManyRequests {
		test.Fatal(response.Code)
	}
}

func TestNativeSteeringCancellationIsNotSuccess(test *testing.T) {
	handler := makeNativeSteeringHandler(func(ctx context.Context, arguments []string) (string, string, int) {
		<-ctx.Done()
		return "steer_drv_status=Success", "", 0
	})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	response := httptest.NewRecorder()
	handler(response, httptest.NewRequest("POST", "/api/v1/steer-native", strings.NewReader(validSteeringBody)).WithContext(ctx))
	if response.Code != http.StatusGatewayTimeout {
		test.Fatal(response.Code)
	}
}

func TestNativeSteeringOutputIsBounded(test *testing.T) {
	var output boundedSteeringOutput
	for repeat := 0; repeat < 3; repeat++ {
		written, err := output.Write([]byte(strings.Repeat("x", 20000)))
		if written != 20000 || err != nil || output.Len() != 16384 {
			test.Fatal(written, err, output.Len())
		}
	}
}

func TestNativeSteeringTimeoutClosesDescendantPipes(test *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, _, code := runNativeSteeringCommand(ctx, "/bin/sh", []string{"-c", "sleep 60 & wait"})
	if code == 0 || time.Since(started) > 2*time.Second {
		test.Fatal("timeout failed to stop the helper process group", code)
	}
}
