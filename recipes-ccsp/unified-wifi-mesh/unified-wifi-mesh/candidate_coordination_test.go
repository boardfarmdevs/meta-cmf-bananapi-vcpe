package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestCoordinationPublishesTheBoundedReadCache(test *testing.T) {
	response := httptest.NewRecorder()
	coordinationHandler(response, httptest.NewRequest("GET", "/api/v1/coordination", nil))
	var payload map[string]interface{}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		test.Fatal(err)
	}
	if liveQueryCacheTTL > 100*time.Millisecond || payload["native_read_cache_ttl_ms"] != float64(100) {
		test.Fatalf("native reads would hide fresh state: %s", response.Body.String())
	}
}

func TestIndependentAgentsRunTogetherAndSameAgentWaits(test *testing.T) {
	coordinator := newCandidateCoordinator(2, 4)
	first, err := coordinator.acquire(context.Background(), "AA")
	if err != nil {
		test.Fatal(err)
	}
	second, err := coordinator.acquire(context.Background(), "BB")
	if err != nil {
		test.Fatal(err)
	}
	defer second()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if release, err := coordinator.acquire(ctx, "aa"); err == nil {
		release()
		test.Fatal("same-agent query overlapped")
	}
	first()
	first()
	release, err := coordinator.acquire(context.Background(), "aa")
	if err != nil {
		test.Fatal(err)
	}
	release()
	if coordinator.waiting != 0 {
		test.Fatal("cancelled waiter leaked")
	}
}

func TestCandidateWaitDoesNotOwnNativeAPI(test *testing.T) {
	coordinator := newCandidateCoordinator(1, 4)
	release, err := coordinator.acquire(context.Background(), "agent")
	if err != nil {
		test.Fatal(err)
	}
	defer release()
	completed := make(chan struct{})
	go func() {
		var timing candidateTiming
		timing.nativeStep(func() { close(completed) })
	}()
	select {
	case <-completed:
	case <-time.After(time.Second):
		test.Fatal("candidate waiter held native API")
	}
}

func TestNativeTreeLifetimeRemainsExclusive(test *testing.T) {
	var workers sync.WaitGroup
	var active int
	var maximum int
	var observed sync.Mutex
	for index := 0; index < 12; index++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			var timing candidateTiming
			timing.nativeStep(func() {
				observed.Lock()
				active++
				if active > maximum {
					maximum = active
				}
				observed.Unlock()
				time.Sleep(time.Millisecond)
				observed.Lock()
				active--
				observed.Unlock()
			})
			if timing.NativeCalls != 1 || timing.NativeMilliseconds <= 0 {
				test.Error("missing native timing")
			}
		}()
	}
	workers.Wait()
	if maximum != 1 {
		test.Fatalf("native ownership overlapped: %d", maximum)
	}
}

func TestCandidateWaitQueueIsBounded(test *testing.T) {
	coordinator := newCandidateCoordinator(1, 0)
	if release, err := coordinator.acquire(context.Background(), "agent"); err == nil {
		release()
		test.Fatal("unbounded admission")
	}
}

func TestCandidatePollsShareOneRecentRead(t *testing.T) {
	clock := time.Unix(1000, 0)
	now := func() time.Time { return clock }
	loads := 0
	share := &candidateStateShare{load: func() candidateState {
		loads++
		return candidateState{metrics: []candidateLinkMetric{{STA: "02:00:00:00:00:01"}}}
	}}
	timing := &candidateTiming{}
	first := share.read(timing, 100*time.Millisecond, now)
	clock = clock.Add(60 * time.Millisecond)
	second := share.read(timing, 100*time.Millisecond, now)
	if loads != 1 || len(first.metrics) != 1 || len(second.metrics) != 1 || timing.NativeCalls != 1 {
		t.Fatalf("a read within the age must be shared: loads=%d calls=%d", loads, timing.NativeCalls)
	}
	clock = clock.Add(60 * time.Millisecond)
	share.read(timing, 100*time.Millisecond, now)
	if loads != 2 || timing.NativeCalls != 2 {
		t.Fatalf("an older read must be replaced: loads=%d calls=%d", loads, timing.NativeCalls)
	}
}

func TestCandidatePollsDoNotKeepAFailedRead(t *testing.T) {
	clock := time.Unix(1000, 0)
	now := func() time.Time { return clock }
	loads := 0
	share := &candidateStateShare{load: func() candidateState {
		loads++
		if loads == 1 {
			return candidateState{err: fmt.Errorf("no tree")}
		}
		return candidateState{}
	}}
	timing := &candidateTiming{}
	if share.read(timing, time.Second, now).err == nil {
		t.Fatal("the failed read must be returned")
	}
	if share.read(timing, time.Second, now).err != nil || loads != 2 {
		t.Fatalf("a failed read must not be shared: loads=%d", loads)
	}
}

func TestConcurrentCandidatePollsWaitForOneRead(t *testing.T) {
	var loads int32
	release := make(chan struct{})
	share := &candidateStateShare{load: func() candidateState {
		atomic.AddInt32(&loads, 1)
		<-release
		return candidateState{}
	}}
	var wg sync.WaitGroup
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			share.read(&candidateTiming{}, time.Second, time.Now)
		}()
	}
	time.Sleep(20 * time.Millisecond)
	close(release)
	wg.Wait()
	if atomic.LoadInt32(&loads) != 1 {
		t.Fatalf("four polls arriving together must make one read, made %d", loads)
	}
}

func TestNotReadyIsResubmittedTwiceWithinTheDeadline(t *testing.T) {
	notReady := fmt.Errorf("native candidate command not accepted: Error_Not_Ready")
	var slept []time.Duration
	sleep := func(d time.Duration) { slept = append(slept, d) }

	// busy twice, then accepted: two retries, counted, the backoff 250 then 500 ms
	calls := 0
	timing := &candidateTiming{}
	err := submitCandidate(timing, func() error {
		calls++
		if calls < 3 {
			return notReady
		}
		return nil
	}, time.Now().Add(8*time.Second), sleep)
	if err != nil || calls != 3 || timing.NotReadyRetries != 2 || timing.NativeCalls != 3 ||
		len(slept) != 2 || slept[0] != 250*time.Millisecond || slept[1] != 500*time.Millisecond {
		t.Fatalf("err=%v calls=%d retries=%d native=%d slept=%v", err, calls, timing.NotReadyRetries,
			timing.NativeCalls, slept)
	}

	// busy every time: the third refusal is returned, not retried again
	calls, slept, timing = 0, nil, &candidateTiming{}
	err = submitCandidate(timing, func() error { calls++; return notReady }, time.Now().Add(8*time.Second), sleep)
	if err == nil || calls != 3 || timing.NotReadyRetries != 2 {
		t.Fatalf("err=%v calls=%d retries=%d", err, calls, timing.NotReadyRetries)
	}

	// another refusal: returned at once
	calls, slept, timing = 0, nil, &candidateTiming{}
	other := fmt.Errorf("native candidate command not accepted: Error_Invalid_Input")
	err = submitCandidate(timing, func() error { calls++; return other }, time.Now().Add(8*time.Second), sleep)
	if err != other || calls != 1 || timing.NotReadyRetries != 0 || len(slept) != 0 {
		t.Fatalf("err=%v calls=%d retries=%d slept=%v", err, calls, timing.NotReadyRetries, slept)
	}

	// no time left for the backoff: returned at once
	calls, slept, timing = 0, nil, &candidateTiming{}
	err = submitCandidate(timing, func() error { calls++; return notReady }, time.Now().Add(100*time.Millisecond), sleep)
	if err == nil || calls != 1 || timing.NotReadyRetries != 0 {
		t.Fatalf("err=%v calls=%d retries=%d", err, calls, timing.NotReadyRetries)
	}

	// accepted at once: no retry
	calls, slept, timing = 0, nil, &candidateTiming{}
	err = submitCandidate(timing, func() error { calls++; return nil }, time.Now().Add(8*time.Second), sleep)
	if err != nil || calls != 1 || timing.NotReadyRetries != 0 || len(slept) != 0 {
		t.Fatalf("err=%v calls=%d retries=%d", err, calls, timing.NotReadyRetries)
	}
}
