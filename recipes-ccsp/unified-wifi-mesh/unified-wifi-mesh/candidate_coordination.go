package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// apiRequestMutex serializes every native libemcli call. Candidate queries
// (the optimizer's unassociated-STA measurements) take it with priority: an
// ordinary API request already holding it finishes, but candidate steps
// waiting for it go before ordinary requests waiting for it. A candidate
// query is several short native steps; queued behind topology, client and
// inventory reads it spent more time waiting than working.
var apiRequestMutex = newNativeLock()

type nativeLock struct {
	mutex           sync.Mutex
	changed         *sync.Cond
	held            bool
	priorityWaiting int
}

func newNativeLock() *nativeLock {
	lock := &nativeLock{}
	lock.changed = sync.NewCond(&lock.mutex)
	return lock
}

func (lock *nativeLock) acquire(priority bool) {
	lock.mutex.Lock()
	if priority {
		lock.priorityWaiting++
	}
	for lock.held || (!priority && lock.priorityWaiting > 0) {
		lock.changed.Wait()
	}
	if priority {
		lock.priorityWaiting--
	}
	lock.held = true
	lock.mutex.Unlock()
}

// Lock takes the native lock behind any waiting candidate step.
func (lock *nativeLock) Lock() { lock.acquire(false) }

// LockPriority takes the native lock ahead of waiting ordinary requests.
func (lock *nativeLock) LockPriority() { lock.acquire(true) }

func (lock *nativeLock) Unlock() {
	lock.mutex.Lock()
	lock.held = false
	lock.changed.Broadcast()
	lock.mutex.Unlock()
}

var candidateRequests = newCandidateCoordinator(1, 32)

const liveQueryCacheTTL = 100 * time.Millisecond

type candidateCoordinator struct {
	mutex          sync.Mutex
	active         map[string]bool
	changed        chan struct{}
	waiting        int
	maximumActive  int
	maximumWaiting int
}

func newCandidateCoordinator(active, waiting int) *candidateCoordinator {
	return &candidateCoordinator{active: make(map[string]bool), changed: make(chan struct{}),
		maximumActive: active, maximumWaiting: waiting}
}

func (coordinator *candidateCoordinator) acquire(ctx context.Context, agent string) (func(), error) {
	agent = strings.ToLower(agent)
	coordinator.mutex.Lock()
	if coordinator.waiting >= coordinator.maximumWaiting {
		coordinator.mutex.Unlock()
		return nil, fmt.Errorf("candidate request queue is full")
	}
	coordinator.waiting++
	for {
		if err := ctx.Err(); err != nil {
			coordinator.waiting--
			coordinator.mutex.Unlock()
			return nil, err
		}
		if !coordinator.active[agent] && len(coordinator.active) < coordinator.maximumActive {
			coordinator.waiting--
			coordinator.active[agent] = true
			coordinator.mutex.Unlock()
			var once sync.Once
			return func() {
				once.Do(func() {
					coordinator.mutex.Lock()
					delete(coordinator.active, agent)
					close(coordinator.changed)
					coordinator.changed = make(chan struct{})
					coordinator.mutex.Unlock()
				})
			}, nil
		}
		changed := coordinator.changed
		coordinator.mutex.Unlock()
		select {
		case <-ctx.Done():
		case <-changed:
		}
		coordinator.mutex.Lock()
	}
}

type candidateTiming struct {
	QueueMilliseconds   float64 `json:"native_queue_ms"`
	NativeMilliseconds  float64 `json:"native_service_ms"`
	NativeCalls         int     `json:"native_calls"`
	ElapsedMilliseconds float64 `json:"elapsed_ms"`
}

func (timing *candidateTiming) nativeStep(action func()) {
	queued := time.Now()
	apiRequestMutex.LockPriority()
	started := time.Now()
	defer apiRequestMutex.Unlock()
	defer func() {
		timing.QueueMilliseconds += float64(started.Sub(queued).Nanoseconds()) / 1e6
		timing.NativeMilliseconds += float64(time.Since(started).Nanoseconds()) / 1e6
		timing.NativeCalls++
	}()
	action()
}

func coordinationHandler(writer http.ResponseWriter, request *http.Request) {
	candidateRequests.mutex.Lock()
	status := map[string]interface{}{
		"schema":                                       "easymesh.cli.coordination.v1",
		"candidate_parallel_agents":                    candidateRequests.maximumActive,
		"candidate_limit_reason":                       "native_controller_command_type_single_flight",
		"candidate_waiting":                            candidateRequests.waiting,
		"candidate_active_agents":                      len(candidateRequests.active),
		"candidate_queue_limit":                        candidateRequests.maximumWaiting,
		"candidate_wait_holds_native_lock":             false,
		"candidate_native_priority":                    true,
		"native_command_and_tree_ownership_serialized": true,
		"native_read_cache_ttl_ms":                     liveQueryCacheTTL.Milliseconds(),
		"http_peer_io_holds_native_lock":              false,
		"http_request_body_limit_bytes":               1024 * 1024,
		"http_response_buffer_limit_bytes":            8 * 1024 * 1024,
		"http_peer_io_timeout_ms":                     5000,
	}
	candidateRequests.mutex.Unlock()
	if nativeSteeringAvailable() {
		status["native_steering_endpoint"] = "/api/v1/steer-native"
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(writer).Encode(status)
}

// candidatePollWait returns the pause before the next read of a submitted
// candidate query. The controller usually completes a query within tens of
// milliseconds, so the first reads come quickly; later reads back off to the
// original 100 ms so a slow agent does not hold the native lock more often.
func candidatePollWait(attempt int) time.Duration {
	early := []time.Duration{10 * time.Millisecond, 20 * time.Millisecond,
		30 * time.Millisecond, 50 * time.Millisecond}
	if attempt < len(early) {
		return early[attempt]
	}
	return 100 * time.Millisecond
}
