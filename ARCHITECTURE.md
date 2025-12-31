# Architecture Diagram: Queue-Based Request Handling

## Before (Race Condition)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Request 1  │     │  Request 2  │     │  Request 3  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │     All hit agent simultaneously      │
       └───────────────────┼───────────────────┘
                           ↓
                    ┌──────────────┐
                    │  /chat       │  ❌ NO PROTECTION
                    │  endpoint    │
                    └──────┬───────┘
                           │
                           ↓
                    ┌──────────────┐
                    │   Agent      │  ⚠️ CONCURRENT ACCESS
                    │   Object     │  ⚠️ CORRUPTED HISTORY
                    └──────────────┘
```

## After (Queue-Based)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Request 1  │     │  Request 2  │     │  Request 3  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │                   │                   │
       ↓                   ↓                   ↓
┌────────────────────────────────────────────────────┐
│              /chat endpoint                        │
│  Creates QueuedRequest with asyncio.Future         │
└─────────────────────┬──────────────────────────────┘
                      │ put()
                      ↓
              ┌────────────────┐
              │                │
              │  asyncio.Queue │  ✓ FIFO ordering
              │                │  ✓ Thread-safe
              │  [Req1]        │
              │  [Req2]        │
              │  [Req3]        │
              │                │
              └────────┬───────┘
                       │ get() - one at a time
                       ↓
              ┌─────────────────────┐
              │  Queue Processor    │
              │  (Background Task)  │
              │                     │
              │  while True:        │
              │    req = await      │
              │      queue.get()    │
              │    process(req)     │
              │    req.future.      │
              │      set_result()   │
              └──────────┬──────────┘
                         │ Sequential access
                         ↓
                  ┌──────────────┐
                  │   Agent      │  ✓ ONE AT A TIME
                  │   Object     │  ✓ SAFE HISTORY
                  └──────────────┘
```

## Flow Diagram

```
Client Request Flow:
───────────────────

1. Client sends request
   │
   ↓
2. /chat endpoint creates Future
   │
   ↓
3. Request added to queue
   │
   ├─→ If queue empty: awaits result
   │
   └─→ If queue has items: awaits result
       │
       └─→ Client connection stays open (long-polling)
   │
   ↓
4. Queue processor picks up request
   │
   ↓
5. Agent processes (takes time)
   │
   ↓
6. Result set in Future
   │
   ↓
7. /chat endpoint gets result
   │
   ↓
8. Response sent to client


Concurrent Scenario:
───────────────────

Time  │ Request 1      │ Request 2      │ Request 3
──────┼────────────────┼────────────────┼──────────────
T0    │ arrives        │                │
T1    │ → queue (1)    │ arrives        │
T2    │ processing...  │ → queue (1)    │ arrives
T3    │ processing...  │ waiting...     │ → queue (2)
T4    │ processing...  │ waiting...     │ waiting...
T5    │ done ✓         │ waiting...     │ waiting...
T6    │                │ processing...  │ waiting...
T7    │                │ processing...  │ waiting...
T8    │                │ done ✓         │ waiting...
T9    │                │                │ processing...
T10   │                │                │ processing...
T11   │                │                │ done ✓

Result: All 3 requests processed successfully, in order,
        with no corruption!
```

## Component Interaction

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI App                          │
│                                                         │
│  ┌──────────────┐         ┌──────────────────────┐    │
│  │ /health      │         │ /chat                │    │
│  │              │         │                      │    │
│  │ Returns:     │         │ 1. Create Future     │    │
│  │ - processing │         │ 2. Queue request     │    │
│  │ - queue_depth│         │ 3. Await Future      │    │
│  └──────────────┘         │ 4. Return result     │    │
│                           └──────────┬───────────┘    │
│                                      │                 │
│                                      ↓                 │
│                           ┌─────────────────────┐     │
│                           │  _request_queue     │     │
│                           │  (asyncio.Queue)    │     │
│                           └──────────┬──────────┘     │
│                                      │                 │
│                                      ↓                 │
│                           ┌─────────────────────┐     │
│                           │  Queue Processor    │     │
│                           │  (Background Task)  │     │
│                           └──────────┬──────────┘     │
│                                      │                 │
└──────────────────────────────────────┼─────────────────┘
                                       │
                                       ↓
                           ┌───────────────────────┐
                           │   Strands Agent       │
                           │   - messages[]        │
                           │   - session_manager   │
                           │   - tools             │
                           └───────────────────────┘
```

## Data Structures

```python
# QueuedRequest dataclass
┌──────────────────────────┐
│ QueuedRequest            │
├──────────────────────────┤
│ message: str             │  ← User's chat message
│ response_future: Future  │  ← Where result goes
└──────────────────────────┘

# Queue state
┌────────────────────────────────┐
│ Global State                   │
├────────────────────────────────┤
│ _request_queue: Queue          │  ← Pending requests
│ _is_processing: bool           │  ← Currently working?
│ _queue_processor_task: Task    │  ← Background worker
└────────────────────────────────┘

# Future communication
Request arrives → Future created → Put in queue → Processor gets it
                                                        ↓
Client waits ← Future resolves ← Result set ← Agent done
```

## State Machine

```
Queue Processor States:
──────────────────────

    ┌─────────┐
    │ IDLE    │ ← Waiting for request
    └────┬────┘
         │ queue.get()
         ↓
    ┌─────────┐
    │PROCESSING│ ← Agent working
    └────┬────┘
         │ set_result()
         ↓
    ┌─────────┐
    │ IDLE    │ ← Ready for next
    └─────────┘

Request States:
──────────────

    ┌─────────┐
    │ QUEUED  │ ← In queue
    └────┬────┘
         │
         ↓
    ┌─────────┐
    │PROCESSING│ ← Agent working
    └────┬────┘
         │
         ↓
    ┌─────────┐
    │  DONE   │ ← Response sent
    └─────────┘
```

## Key Properties

✅ **Mutual Exclusion**: Only one request processes at a time  
✅ **Progress**: Queue always moves forward (no deadlock)  
✅ **Fairness**: FIFO ordering (first come, first served)  
✅ **Resilience**: Errors don't block queue  
✅ **Observable**: Queue depth visible  
✅ **Clean Shutdown**: Graceful task cancellation  
