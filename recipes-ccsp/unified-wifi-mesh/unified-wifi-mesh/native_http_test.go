package main

import (
	"bytes"
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type stalledHTTPWriter struct {
	*httptest.ResponseRecorder
	entered chan struct{}
	release chan struct{}
}

func (writer *stalledHTTPWriter) Write(data []byte) (int, error) {
	close(writer.entered)
	<-writer.release
	return writer.ResponseRecorder.Write(data)
}

func TestNativeOwnershipDoesNotIncludeSlowResponseReaders(test *testing.T) {
	handler := withNativeAPIOwnership(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		_, _ = writer.Write([]byte("native result"))
	}))
	slow := &stalledHTTPWriter{httptest.NewRecorder(), make(chan struct{}), make(chan struct{})}
	completed := make(chan struct{})
	go func() { handler.ServeHTTP(slow, httptest.NewRequest("GET", "/api/v1/topology", nil)); close(completed) }()
	<-slow.entered
	defer func() { close(slow.release); <-completed }()
	fast := make(chan struct{})
	go func() {
		handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/api/v1/clients", nil))
		close(fast)
	}()
	select {
	case <-fast:
	case <-time.After(time.Second):
		test.Fatal("slow response held native ownership")
	}
}

func TestNativeOwnershipDoesNotIncludeSlowRequestBodies(test *testing.T) {
	reader, writer := io.Pipe()
	completed := make(chan struct{})
	handler := withNativeAPIOwnership(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.WriteHeader(http.StatusNoContent)
	}))
	go func() {
		handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("POST", "/api/v1/settings", reader))
		close(completed)
	}()
	defer func() { writer.Close(); <-completed }()
	fast := make(chan struct{})
	go func() {
		handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/api/v1/topology", nil))
		close(fast)
	}()
	select {
	case <-fast:
	case <-time.After(time.Second):
		test.Fatal("slow request body held native ownership")
	}
}

func TestNativeHTTPBuffersHaveFiniteBounds(test *testing.T) {
	called := false
	handler := withNativeAPIOwnership(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		called = true
		_, _ = writer.Write(bytes.Repeat([]byte("x"), 8*1024*1024+1))
	}))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("POST", "/api/v1/settings", strings.NewReader(strings.Repeat("x", 1024*1024+1))))
	if called || response.Code != http.StatusBadRequest {
		test.Fatal("oversized request entered native code")
	}
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("GET", "/api/v1/topology", nil))
	if !called || response.Code != http.StatusInternalServerError || response.Body.Len() > 100 {
		test.Fatal("oversized response escaped the bounded buffer")
	}
}

func TestCancelledNativeHTTPRequestDoesNotExecute(test *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	called := false
	response := httptest.NewRecorder()
	withNativeAPIOwnership(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true })).ServeHTTP(
		response, httptest.NewRequest("GET", "/api/v1/topology", nil).WithContext(ctx))
	if called || response.Code != http.StatusRequestTimeout {
		test.Fatal("cancelled request entered native code")
	}
}

func TestNativeHTTPRealSlowReaderDoesNotBlockOtherRequests(test *testing.T) {
	entered := make(chan struct{})
	handler := withNativeAPIOwnership(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/slow" {
			_, _ = writer.Write(bytes.Repeat([]byte("x"), 8*1024*1024))
			close(entered)
			return
		}
		_, _ = writer.Write([]byte("ready"))
	}))
	server := httptest.NewUnstartedServer(handler)
	server.Config.ConnContext = labHTTPServer(handler).ConnContext
	server.Start()
	defer server.Close()
	connection, err := net.Dial("tcp", server.Listener.Addr().String())
	if err != nil {
		test.Fatal(err)
	}
	defer connection.Close()
	if tcp, ok := connection.(*net.TCPConn); ok {
		_ = tcp.SetReadBuffer(1024)
	}
	_, _ = io.WriteString(connection, "GET /slow HTTP/1.1\r\nHost: localhost\r\n\r\n")
	select {
	case <-entered:
	case <-time.After(time.Second):
		test.Fatal("slow request did not enter")
	}
	client := &http.Client{Timeout: time.Second}
	response, err := client.Get(server.URL + "/fast")
	if err != nil {
		test.Fatal(err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil || string(body) != "ready" {
		test.Fatalf("slow reader blocked native API: %q %v", body, err)
	}
}
