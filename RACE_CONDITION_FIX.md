# Fix: Race Condition in Concurrent Request Handling

## Problem

The `/chat` endpoint in `docker/agent_runner.py` had no protection against concurrent requests. When multiple messages were sent while an agent was processing, both would hit the same Agent object simultaneously, causing:

1. **Corrupted conversation history** - Multiple requests modifying the message list concurrently
2. **Race conditions** - Unpredictable behavior when agent state is accessed by multiple requests
3. **Lost requests** - Requests could interfere with each other's processing

The `_is_processing` flag was only used for status reporting, not for blocking concurrent access.

## Solution

Implemented **Option A: Request Queue** - the most user-friendly approach that:

1. Uses `asyncio.Queue` to queue incoming chat requests
2. Processes requests sequentially through a dedicated background task
3. Each request waits for its turn but gets a proper response
4. Provides queue depth visibility in the `/health` endpoint

## Changes

### 1. Added Queue Infrastructure

- **`QueuedRequest` dataclass**: Pairs a message with an `asyncio.Future` for response delivery
- **`_request_queue`**: Global `asyncio.Queue` to hold pending requests
- **`_queue_processor_task`**: Background task that processes the queue

### 2. Queue Processor (`process_request_queue`)

- Runs continuously in the background
- Pulls requests from the queue one at a time
- Processes each request with the agent
- Sets the result in the request's future
- Handles errors gracefully without stopping the queue
- Properly sets `_is_processing` flag during execution

### 3. Updated `/chat` Endpoint

- Creates a `QueuedRequest` with a future for the response
- Adds request to the queue
- Waits for the future to be resolved by the queue processor
- Returns the result when processing completes
- Logs queue status for monitoring

### 4. Enhanced `/health` Endpoint

- Now includes `queue_depth` to show pending requests
- Useful for monitoring system load and queue buildup

### 5. Lifecycle Management

- **Startup**: Initializes queue and starts processor task
- **Shutdown**: Cleanly cancels processor task

## Benefits

✅ **Thread-safe**: Only one request processes at a time  
✅ **No data corruption**: Conversation history remains consistent  
✅ **All requests served**: No rejected requests, just queued  
✅ **Observable**: Queue depth visible in health endpoint  
✅ **Clean shutdown**: Proper async task cancellation  
✅ **Error resilient**: Queue continues even if one request fails  

## Testing

Use the provided `test_concurrent_requests.py` script to verify:

```bash
# Start the agent container first, then:
python test_concurrent_requests.py
```

The test:
1. Sends 5 concurrent requests rapidly
2. Verifies all process sequentially
3. Confirms no race conditions
4. Shows queue depth during processing

## Alternatives Considered

- **Option B (Reject)**: Return error if `_is_processing` is True
  - ❌ Bad UX - clients have to implement retry logic
  
- **Option C (Lock)**: Use `asyncio.Lock` around agent invocation
  - ⚠️ Similar to queue but less observable
  - ⚠️ No visibility into pending request count

**Queue approach chosen for best UX and observability.**

## Backwards Compatibility

✅ Fully backwards compatible:
- Same API contract
- Same response format
- Transparent queuing (clients don't need changes)
- Only adds `queue_depth` to health response (additive change)
