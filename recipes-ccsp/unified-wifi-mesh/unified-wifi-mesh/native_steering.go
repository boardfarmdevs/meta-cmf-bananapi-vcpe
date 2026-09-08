package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type nativeSteeringRequest struct {
	Station        string `json:"station"`
	Source         string `json:"source_bssid"`
	Target         string `json:"target_bssid"`
	OperatingClass int    `json:"operating_class"`
	Channel        int    `json:"channel"`
}

func (request *nativeSteeringRequest) arguments() ([]string, error) {
	for _, field := range []*string{&request.Station, &request.Source, &request.Target} {
		address, err := net.ParseMAC(*field)
		if err != nil || len(address) != 6 {
			return nil, fmt.Errorf("invalid six-byte MAC address")
		}
		*field = address.String()
	}
	validChannel := false
	switch request.OperatingClass {
	case 81:
		validChannel = request.Channel >= 1 && request.Channel <= 13
	case 115:
		validChannel = request.Channel >= 36 && request.Channel <= 48 && request.Channel%4 == 0
	case 118:
		validChannel = request.Channel >= 52 && request.Channel <= 64 && request.Channel%4 == 0
	case 121:
		validChannel = request.Channel >= 100 && request.Channel <= 144 && request.Channel%4 == 0
	case 124:
		validChannel = request.Channel >= 149 && request.Channel <= 161 && request.Channel%4 == 1
	case 125:
		validChannel = request.Channel >= 165 && request.Channel <= 177 && request.Channel%4 == 1
	case 131:
		validChannel = request.Channel >= 1 && request.Channel <= 233 && request.Channel%4 == 1
	}
	if !validChannel || request.Source == request.Target {
		return nil, fmt.Errorf("invalid target or channel")
	}
	return []string{request.Station, request.Target, strconv.Itoa(request.OperatingClass), strconv.Itoa(request.Channel), "gentle", request.Source}, nil
}

type boundedSteeringOutput struct{ bytes.Buffer }

func (output *boundedSteeringOutput) Write(data []byte) (int, error) {
	length := len(data)
	remaining := 16384 - output.Len()
	if remaining > 0 {
		if len(data) > remaining {
			data = data[:remaining]
		}
		_, _ = output.Buffer.Write(data)
	}
	return length, nil
}

type nativeSteeringRunner func(context.Context, []string) (string, string, int)

func runNativeSteering(ctx context.Context, arguments []string) (string, string, int) {
	return runNativeSteeringCommand(ctx, "/usr/bin/steer.sh", arguments)
}

func runNativeSteeringCommand(ctx context.Context, program string, arguments []string) (string, string, int) {
	if err := ctx.Err(); err != nil {
		return "", err.Error(), 1
	}
	command := exec.Command(program, arguments...)
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	var stdout, stderr boundedSteeringOutput
	command.Stdout, command.Stderr = &stdout, &stderr
	err := command.Start()
	if err == nil {
		completed := make(chan error, 1)
		go func() { completed <- command.Wait() }()
		select {
		case err = <-completed:
		case <-ctx.Done():
			if killError := syscall.Kill(-command.Process.Pid, syscall.SIGKILL); killError != nil {
				_ = command.Process.Kill()
			}
			err = <-completed
		}
	}
	code := 0
	if err != nil {
		code = 1
		if command.ProcessState != nil {
			code = command.ProcessState.ExitCode()
		}
		_, _ = stderr.Write([]byte("\n" + err.Error()))
	}
	return stdout.String(), stderr.String(), code
}

func nativeSteeringAvailable() bool {
	for _, path := range []string{"/usr/bin/steer.sh", "/usr/bin/steer_drv"} {
		info, err := os.Stat(path)
		if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0111 == 0 {
			return false
		}
	}
	return true
}

func makeNativeSteeringHandler(runner nativeSteeringRunner) http.HandlerFunc {
	slots := make(chan struct{}, 1)
	return func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.Header().Set("Cache-Control", "no-store")
		respond := func(code int, value interface{}) { writer.WriteHeader(code); _ = json.NewEncoder(writer).Encode(value) }
		fail := func(code int, message string) {
			respond(code, map[string]interface{}{"success": false, "message": message})
		}
		if request.Method != http.MethodPost {
			fail(http.StatusMethodNotAllowed, "POST required")
			return
		}
		var payload nativeSteeringRequest
		decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 4096))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil {
			fail(http.StatusBadRequest, err.Error())
			return
		}
		var trailing interface{}
		if decoder.Decode(&trailing) != io.EOF {
			fail(http.StatusBadRequest, "one JSON request required")
			return
		}
		arguments, err := payload.arguments()
		if err != nil {
			fail(http.StatusBadRequest, err.Error())
			return
		}
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			fail(http.StatusTooManyRequests, "native steering submission already active")
			return
		}
		started := time.Now()
		ctx, cancel := context.WithTimeout(request.Context(), 15*time.Second)
		defer cancel()
		stdout, stderr, returncode := runner(ctx, arguments)
		statuses := []string{}
		for _, line := range strings.Split(stdout, "\n") {
			if strings.HasPrefix(line, "steer_drv_status=") {
				statuses = append(statuses, strings.TrimPrefix(line, "steer_drv_status="))
			}
		}
		success := returncode == 0 && len(statuses) == 1 && statuses[0] == "Success" && ctx.Err() == nil
		code := http.StatusOK
		if !success {
			code = http.StatusServiceUnavailable
		}
		if ctx.Err() != nil {
			code = http.StatusGatewayTimeout
		}
		respond(code, map[string]interface{}{"success": success, "returncode": returncode,
			"stdout": stdout, "stderr": stderr, "transport": "controller-local-helper",
			"elapsed_ms": float64(time.Since(started).Nanoseconds()) / 1e6})
	}
}

var nativeSteeringHandler = makeNativeSteeringHandler(runNativeSteering)
