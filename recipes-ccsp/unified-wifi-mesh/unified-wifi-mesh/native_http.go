package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"time"
)

type nativeConnectionKey struct{}

func labHTTPServer(handler http.Handler) *http.Server {
	return &http.Server{Addr: "0.0.0.0:8888", Handler: handler,
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
		if request.URL.Path == "/api/v1/ws" || request.URL.Path == "/api/v1/coordination" || request.Method == http.MethodOptions {
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
