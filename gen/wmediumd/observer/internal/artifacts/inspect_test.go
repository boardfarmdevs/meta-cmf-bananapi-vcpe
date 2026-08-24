package artifacts

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestInspectConfigAndCurrentProcess(t *testing.T) {
	directory := t.TempDir()
	config := filepath.Join(directory, "wmediumd.cfg")
	pidFile := filepath.Join(directory, "wmediumd.pid")
	if err := os.WriteFile(config, []byte("model = snr\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pidFile, []byte(fmt.Sprintf("%d\n", os.Getpid())), 0o600); err != nil {
		t.Fatal(err)
	}
	inspector := &Inspector{ConfigPath: config, PIDFile: pidFile}
	artifacts := inspector.Inspect()
	want := fmt.Sprintf("%x", sha256.Sum256([]byte("model = snr\n")))
	if !artifacts.StartupConfig.Available || artifacts.StartupConfig.SHA256 != want {
		t.Fatalf("unexpected config artifact: %+v", artifacts.StartupConfig)
	}
	if !artifacts.DaemonBinary.Available || artifacts.DaemonBinary.SHA256 == "" {
		t.Fatalf("unexpected binary artifact: %+v", artifacts.DaemonBinary)
	}
	wantProcPath := fmt.Sprintf("/proc/%d/exe", os.Getpid())
	resolved, err := os.Readlink(wantProcPath)
	if err != nil {
		t.Fatal(err)
	}
	if artifacts.DaemonBinary.Path != wantProcPath || artifacts.DaemonBinary.ResolvedPath != strings.TrimSuffix(resolved, " (deleted)") {
		t.Fatalf("binary was not hashed through procfs: %+v", artifacts.DaemonBinary)
	}
}
