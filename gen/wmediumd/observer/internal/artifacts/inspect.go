package artifacts

import (
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"github.com/boardfarmdevs/meta-cmf-bananapi-vcpe/gen/wmediumd/observer/internal/model"
)

// Inspector caches hashes by path and file identity. Artifact failures enrich
// a snapshot but never make live readback unavailable.
type Inspector struct {
	ConfigPath string
	PIDFile    string

	mu    sync.Mutex
	cache map[string]cacheEntry
}

type cacheEntry struct {
	size    int64
	modTime int64
	result  model.Artifact
}

func (i *Inspector) Inspect() model.Artifacts {
	i.mu.Lock()
	defer i.mu.Unlock()
	if i.cache == nil {
		i.cache = make(map[string]cacheEntry)
	}
	return model.Artifacts{
		StartupConfig: i.inspectFile(i.ConfigPath),
		DaemonBinary:  i.inspectDaemon(),
	}
}

func (i *Inspector) inspectDaemon() model.Artifact {
	if i.PIDFile == "" {
		return model.Artifact{Error: "PID file path is not configured"}
	}
	value, err := os.ReadFile(i.PIDFile)
	if err != nil {
		return model.Artifact{Path: i.PIDFile, Error: err.Error()}
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(value)))
	if err != nil || pid <= 0 {
		return model.Artifact{Path: i.PIDFile, Error: "invalid daemon PID"}
	}
	procExecutable := fmt.Sprintf("/proc/%d/exe", pid)
	executable, err := os.Readlink(procExecutable)
	if err == nil {
		// Open the procfs executable handle itself. This preserves hashing when
		// systemd ProtectHome hides the daemon's /home checkout path inside the
		// Console mount namespace. Keep the human-resolved path as metadata.
		result := i.inspectFile(procExecutable)
		result.ResolvedPath = strings.TrimSuffix(executable, " (deleted)")
		return result
	}
	if err != nil {
		// Ubuntu may deny /proc/PID/exe for a root-owned process while leaving
		// its non-sensitive cmdline readable. The first argument is the exact
		// executable path used by the accepted launcher.
		cmdline, cmdlineErr := os.ReadFile(fmt.Sprintf("/proc/%d/cmdline", pid))
		if cmdlineErr != nil {
			return model.Artifact{Path: fmt.Sprintf("/proc/%d/exe", pid), Error: err.Error()}
		}
		if separator := strings.IndexByte(string(cmdline), 0); separator >= 0 {
			cmdline = cmdline[:separator]
		}
		executable = string(cmdline)
		if executable == "" || !filepath.IsAbs(executable) {
			return model.Artifact{Path: fmt.Sprintf("/proc/%d/exe", pid), Error: "cannot resolve an absolute daemon executable"}
		}
	}
	return i.inspectFile(strings.TrimSuffix(executable, " (deleted)"))
}

func (i *Inspector) inspectFile(path string) model.Artifact {
	if path == "" {
		return model.Artifact{Error: "path is not configured"}
	}
	clean := filepath.Clean(path)
	info, err := os.Stat(clean)
	if err != nil {
		return model.Artifact{Path: clean, Error: err.Error()}
	}
	key := clean
	if cached, ok := i.cache[key]; ok && cached.size == info.Size() && cached.modTime == info.ModTime().UnixNano() {
		return cached.result
	}
	file, err := os.Open(clean)
	if err != nil {
		return model.Artifact{Path: clean, Error: err.Error()}
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return model.Artifact{Path: clean, Error: err.Error()}
	}
	result := model.Artifact{Path: clean, SHA256: fmt.Sprintf("%x", hash.Sum(nil)), Available: true}
	i.cache[key] = cacheEntry{size: info.Size(), modTime: info.ModTime().UnixNano(), result: result}
	return result
}
