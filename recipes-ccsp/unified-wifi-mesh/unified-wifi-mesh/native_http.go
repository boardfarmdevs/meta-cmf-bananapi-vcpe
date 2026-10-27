package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"time"
)

type nativeConnectionKey struct{}

// The web UI's address when its environment names none: every address, as before.
const defaultListenAddress = "0.0.0.0:8888"

// listenAddress is the web UI's address from EM_CLI_LISTEN (value, and whether it is set): an IP
// literal and a port, "127.0.0.1:8888" or "[::1]:8888". Unset, the default. Set but empty or
// anything else is an error, never the default: an image that asks for loopback must not end up
// serving the LAN.
func listenAddress(value string, set bool) (string, error) {
	if !set {
		return defaultListenAddress, nil
	}
	host, port, err := net.SplitHostPort(value)
	if err != nil {
		return "", fmt.Errorf("EM_CLI_LISTEN %q: %v", value, err)
	}
	if net.ParseIP(host) == nil {
		return "", fmt.Errorf("EM_CLI_LISTEN %q: the host is not an IP address", value)
	}
	if number, err := strconv.Atoi(port); err != nil || number < 1 || number > 65535 {
		return "", fmt.Errorf("EM_CLI_LISTEN %q: the port is not 1 to 65535", value)
	}
	return net.JoinHostPort(host, port), nil
}

func labHTTPServer(handler http.Handler, address string) *http.Server {
	return &http.Server{Addr: address, Handler: handler,
		ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 65536,
		ConnContext: func(ctx context.Context, connection net.Conn) context.Context {
			return context.WithValue(ctx, nativeConnectionKey{}, connection)
		}}
}

type nativeHTTPResponse struct {
	header http.Header
	body   bytes.Buffer
	status int
	failed bool
}

func (response *nativeHTTPResponse) Header() http.Header { return response.header }

func (response *nativeHTTPResponse) WriteHeader(status int) {
	if response.status == 0 {
		response.status = status
	}
}

func (response *nativeHTTPResponse) Write(data []byte) (int, error) {
	if response.body.Len()+len(data) > 8*1024*1024 {
		response.failed = true
		return 0, fmt.Errorf("native API response exceeds bounded buffer")
	}
	response.WriteHeader(http.StatusOK)
	return response.body.Write(data)
}

func withNativeAPIOwnership(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/api/v1/ws" || request.URL.Path == "/api/v1/coordination" || request.URL.Path == "/api/v1/room-layout" || request.Method == http.MethodOptions {
			next.ServeHTTP(writer, request)
			return
		}
		connection, _ := request.Context().Value(nativeConnectionKey{}).(net.Conn)
		if connection != nil {
			_ = connection.SetReadDeadline(time.Now().Add(5 * time.Second))
			defer connection.SetReadDeadline(time.Time{})
		}
		if request.Body != nil {
			body, err := io.ReadAll(http.MaxBytesReader(writer, request.Body, 1024*1024))
			_ = request.Body.Close()
			if err != nil {
				http.Error(writer, "invalid, oversized or timed-out API body", http.StatusBadRequest)
				return
			}
			request.Body = io.NopCloser(bytes.NewReader(body))
		}
		if connection != nil {
			_ = connection.SetReadDeadline(time.Time{})
		}
		response := &nativeHTTPResponse{header: make(http.Header)}
		queued := time.Now()
		serve := func() {
			if request.Context().Err() != nil {
				response.WriteHeader(http.StatusRequestTimeout)
				return
			}
			next.ServeHTTP(response, request)
		}
		if request.URL.Path == "/api/v1/unassoc_sta_query" || request.URL.Path == "/api/v1/steer-native" {
			serve()
		} else {
			func() {
				apiRequestMutex.Lock()
				defer apiRequestMutex.Unlock()
				started := time.Now()
				response.header.Set("X-Lab-Native-Queue-Ms", fmt.Sprintf("%.3f", float64(started.Sub(queued).Nanoseconds())/1e6))
				serve()
				response.header.Set("X-Lab-Native-Service-Ms", fmt.Sprintf("%.3f", float64(time.Since(started).Nanoseconds())/1e6))
			}()
		}
		if connection != nil {
			_ = connection.SetWriteDeadline(time.Now().Add(5 * time.Second))
			defer connection.SetWriteDeadline(time.Time{})
		}
		if response.failed {
			http.Error(writer, "native API response exceeds bounded buffer", http.StatusInternalServerError)
			return
		}
		for name, values := range response.header {
			writer.Header()[name] = append([]string(nil), values...)
		}
		if response.status == 0 {
			response.status = http.StatusOK
		}
		writer.WriteHeader(response.status)
		_, _ = writer.Write(response.body.Bytes())
		if flusher, ok := writer.(http.Flusher); ok {
			flusher.Flush()
		}
	})
}
