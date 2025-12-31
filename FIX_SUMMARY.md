# Summary: Race Condition Fix for Containerized Strands Agents

## Branch
`fix/concurrent-request-handling`

## Commits
1. `7af35de` - Fix race condition in concurrent request handling
2. `016d812` - Add unit test for queue-based request handling

## Problem Identified

The `/chat` endpoint in `docker/agent_runner.py` had a critical race condition:

- **No concurrency protection**: Multiple requests could hit the same Agent object simultaneously
- **Corrupted conversation history**: Concurrent modifications to `agent.messages` list
- **Unpredictable behavior**: Race conditions when agent state accessed by multiple requests
- **Ineffective flag**: `_is_processing` was only for status reporting, not blocking

### Specific Issues:
```python
# BEFORE - No protection against concurrent access
@app.post("/chat")
async def chat(request: ChatRequest):
    global _is_processing
    _is_processing = True  # ❌ Doesn't block other requests!
    
    agent = get_agent()
    response = await invoke_agent_with_retry(agent, request.message)
    # ⚠️ Multiple requests can reach here simultaneously
    
    _is_processing = False
    return response
```

## Solution Implemented: Option A (Queue-Based)

Chose **Option A** over simpler alternatives because:
- ✅ Best user experience (no rejected requests)
- ✅ Observable (queue depth visible)
- ✅ Predictable (FIFO ordering)
- ✅ Resilient (errors don't stop queue)

### Key Components:

#### 1. Request Queue Infrastructure
```python
@dataclass
class QueuedRequest:
    message: str
    response_future: asyncio.Future

_request_queue: asyncio.Queue
_queue_processor_task: asyncio.Task
```

#### 2. Background Queue Processor
- Runs continuously in `asyncio.create_task()`
- Pulls one request at a time from queue
- Processes with agent sequentially
- Returns result via `asyncio.Future`
- Handles errors without stopping

#### 3. Updated Chat Endpoint
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    # Create future for response
    response_future = asyncio.Future()
    queued_request = QueuedRequest(request.message, response_future)
    
    # Add to queue
    await _request_queue.put(queued_request)
    
    # Wait for result (blocks until processed)
    result = await response_future
    return ChatResponse(**result)
```

#### 4. Enhanced Health Endpoint
```python
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent_id": AGENT_ID,
        "processing": _is_processing,
        "queue_depth": _request_queue.qsize(),  # NEW
    }
```

## Files Changed

### Modified:
- `docker/agent_runner.py` - Core fix implementation

### Added:
- `RACE_CONDITION_FIX.md` - Detailed documentation
- `test_concurrent_requests.py` - Integration test (requires running container)
- `test_queue_unit.py` - Unit test (standalone verification)

## Testing

### Unit Test (`test_queue_unit.py`)
```bash
python test_queue_unit.py
```
**Result**: ✅ All tests passed
- Sequential processing verified
- Order preservation confirmed
- No duplicate/corrupted responses
- Error resilience validated

### Integration Test (`test_concurrent_requests.py`)
```bash
# Requires running agent container
python test_concurrent_requests.py
```
Sends 5 concurrent requests and verifies:
- All process without errors
- Each gets unique response
- Queue depth reported correctly
- No race conditions

## Technical Details

### Concurrency Pattern
- **Producer**: `/chat` endpoint adds to queue
- **Consumer**: Background task processes queue
- **Communication**: `asyncio.Future` for response delivery
- **Guarantee**: Strictly sequential processing

### Lifecycle Management
```python
# Startup
@app.on_event("startup")
async def startup():
    _request_queue = asyncio.Queue()
    _queue_processor_task = asyncio.create_task(process_request_queue())

# Shutdown
@app.on_event("shutdown")
async def shutdown():
    _queue_processor_task.cancel()
    await _queue_processor_task  # Clean cancellation
```

### Error Handling
- Errors in one request don't affect others
- Error messages saved to conversation history
- Queue processor continues after errors
- Clean shutdown with `CancelledError` handling

## Benefits

| Benefit | Description |
|---------|-------------|
| **Thread-Safety** | Only one request accesses agent at a time |
| **Data Integrity** | Conversation history never corrupted |
| **Reliability** | All requests eventually processed |
| **Observability** | Queue depth visible for monitoring |
| **Clean Code** | Clear separation of concerns |
| **Testable** | Easy to unit test without container |

## Alternatives Considered

### Option B: Reject Concurrent Requests
```python
if _is_processing:
    raise HTTPException(503, "Agent busy")
```
- ❌ Bad UX - client must retry
- ❌ Request loss possible
- ✅ Simpler implementation

### Option C: Lock-Based
```python
_lock = asyncio.Lock()

async with _lock:
    response = await agent(message)
```
- ✅ Prevents race condition
- ❌ No visibility into waiting requests
- ❌ Less observable than queue

**Queue chosen for superior UX and observability.**

## Backwards Compatibility

✅ **Fully backwards compatible:**
- Same API contract
- Same request/response format
- Transparent queuing (clients unaware)
- Only adds `queue_depth` to health (additive)

## Performance Impact

- **Throughput**: Unchanged (was already sequential due to agent processing time)
- **Latency**: Minimal overhead (queue operations are O(1))
- **Memory**: Grows linearly with queue depth (typically small)
- **CPU**: Negligible (async queue is efficient)

## Deployment Notes

No special deployment steps needed:
1. Build new Docker image
2. Deploy as usual
3. Existing clients work unchanged
4. Monitor `queue_depth` in health endpoint

## Monitoring Recommendations

Watch for:
- **High `queue_depth`**: May indicate overload
- **Always `processing=true`**: Agent may be stuck
- **Growing queue over time**: Throughput < arrival rate

## Future Enhancements (Optional)

Could add:
- Queue size limits (reject after N pending)
- Request timeout (fail if queued too long)
- Priority queue (different request priorities)
- Metrics (queue wait time, processing time)

## Conclusion

This fix eliminates the race condition while maintaining excellent UX:
- ✅ No rejected requests
- ✅ Clean, testable implementation
- ✅ Observable system behavior
- ✅ Backwards compatible
- ✅ Production ready

Ready to merge! 🚀
