package main

import (
	"net"
	"net/http"
	"testing"
	"time"
)

func TestListenAddressUnsetIsEveryAddress(test *testing.T) {
	address, err := listenAddress("", false)
	if err != nil || address != "0.0.0.0:8888" {
		test.Fatalf("unset: %q, %v", address, err)
	}
}

func TestListenAddressTakesAnIPAndAPort(test *testing.T) {
	for value, want := range map[string]string{
		"127.0.0.1:8888": "127.0.0.1:8888",
		"[::1]:8888":     "[::1]:8888",
		"0.0.0.0:8888":   "0.0.0.0:8888",
		"10.0.0.1:18888": "10.0.0.1:18888",
	} {
		address, err := listenAddress(value, true)
		if err != nil || address != want {
			test.Errorf("%q: %q, %v", value, address, err)
		}
	}
}

func TestListenAddressRefusesAnythingElseWhenSet(test *testing.T) {
	// set but empty or wrong is never the default: the UI must not start on every address
	for _, value := range []string{
		"", " ", "8888", ":8888", "127.0.0.1", "localhost:8888", "127.0.0.1:0",
		"127.0.0.1:65536", "127.0.0.1:http", "::1:8888", "fe80::1%br0:8888", "127.0.0.1:8888 ",
	} {
		if address, err := listenAddress(value, true); err == nil {
			test.Errorf("%q accepted as %q", value, address)
		}
	}
}

func TestTheServerListensOnlyWhereItIsTold(test *testing.T) {
	// the address the server is given is the one it binds: loopback here, so no other address
	// of the host reaches it
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		test.Fatal(err)
	}
	address := listener.Addr().String()
	listener.Close()
	server := labHTTPServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte("ready"))
	}), address)
	if server.Addr != address {
		test.Fatalf("server address %q, want %q", server.Addr, address)
	}
	go func() { _ = server.ListenAndServe() }()
	defer server.Close()
	deadline := time.Now().Add(5 * time.Second)
	for {
		connection, err := net.Dial("tcp", address)
		if err == nil {
			connection.Close()
			break
		}
		if time.Now().After(deadline) {
			test.Fatalf("no answer on %s: %v", address, err)
		}
		time.Sleep(50 * time.Millisecond)
	}
}
