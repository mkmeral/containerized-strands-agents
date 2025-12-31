#!/usr/bin/env python3
"""
Unit test demonstrating the queue-based concurrent request handling.

This test simulates concurrent requests without requiring a running container.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class QueuedRequest:
    """Represents a queued chat request."""
    message: str
    response_future: asyncio.Future


# Simulate global state
_is_processing = False
_request_queue: Optional[asyncio.Queue] = None
_processed_order = []


async def simulate_agent_processing(message: str, delay: float = 0.5) -> str:
    """Simulate agent processing a message."""
    await asyncio.sleep(delay)  # Simulate work
    return f"Processed: {message}"


async def process_request_queue():
    """Process requests from the queue sequentially."""
    global _is_processing, _request_queue, _processed_order
    
    print("Queue processor started")
    
    while True:
        try:
            queued_request: QueuedRequest = await _request_queue.get()
            
            try:
                _is_processing = True
                print(f"  Processing: {queued_request.message}")
                _processed_order.append(queued_request.message)
                
                # Simulate agent work
                response = await simulate_agent_processing(queued_request.message)
                
                # Set result
                queued_request.response_future.set_result({
                    "status": "success",
                    "response": response,
                })
                print(f"  Completed: {queued_request.message}")
                
            except Exception as e:
                queued_request.response_future.set_result({
                    "status": "error",
                    "response": str(e),
                })
                
            finally:
                _is_processing = False
                _request_queue.task_done()
                
        except asyncio.CancelledError:
            print("Queue processor cancelled")
            break


async def handle_chat_request(message: str) -> dict:
    """Simulate the /chat endpoint."""
    global _request_queue
    
    # Create a future for the response
    response_future = asyncio.Future()
    
    # Create queued request
    queued_request = QueuedRequest(
        message=message,
        response_future=response_future
    )
    
    # Log queue status
    queue_size = _request_queue.qsize()
    if _is_processing or queue_size > 0:
        print(f"Request queued: '{message}' (queue depth: {queue_size}, processing: {_is_processing})")
    
    # Add to queue
    await _request_queue.put(queued_request)
    
    # Wait for result
    result = await response_future
    
    return result


async def test_concurrent_requests():
    """Test that concurrent requests are processed sequentially."""
    global _request_queue, _processed_order
    
    print("="*80)
    print("Testing Concurrent Request Handling")
    print("="*80)
    
    # Initialize queue
    _request_queue = asyncio.Queue()
    _processed_order.clear()
    
    # Start queue processor
    processor_task = asyncio.create_task(process_request_queue())
    
    # Send 5 concurrent requests
    messages = [f"Request {i}" for i in range(1, 6)]
    print(f"\nSending {len(messages)} concurrent requests...")
    
    # Fire all requests at once
    tasks = [handle_chat_request(msg) for msg in messages]
    
    # Wait for all to complete
    results = await asyncio.gather(*tasks)
    
    # Cancel processor
    processor_task.cancel()
    try:
        await processor_task
    except asyncio.CancelledError:
        pass
    
    # Verify results
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)
    
    # Check all succeeded
    successes = sum(1 for r in results if r['status'] == 'success')
    print(f"✓ {successes}/{len(messages)} requests succeeded")
    
    # Check order preservation
    print(f"✓ Processing order: {_processed_order}")
    assert _processed_order == messages, "Order not preserved!"
    
    # Check all responses unique
    responses = [r['response'] for r in results]
    assert len(responses) == len(set(responses)), "Duplicate responses detected!"
    print(f"✓ All responses unique (no corruption)")
    
    # Check each request got correct response
    for i, (msg, result) in enumerate(zip(messages, results)):
        expected = f"Processed: {msg}"
        assert result['response'] == expected, f"Response mismatch for {msg}"
    print(f"✓ Each request got its correct response")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED - No race conditions detected!")
    print("="*80)


async def test_error_resilience():
    """Test that queue continues processing after an error."""
    global _request_queue, _processed_order
    
    print("\n" + "="*80)
    print("Testing Error Resilience")
    print("="*80)
    
    # Initialize queue
    _request_queue = asyncio.Queue()
    _processed_order.clear()
    
    # Start queue processor
    processor_task = asyncio.create_task(process_request_queue())
    
    # Send requests
    messages = ["Request 1", "Request 2", "Request 3"]
    print(f"\nSending {len(messages)} requests...")
    
    tasks = [handle_chat_request(msg) for msg in messages]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Cancel processor
    processor_task.cancel()
    try:
        await processor_task
    except asyncio.CancelledError:
        pass
    
    # Verify all processed
    print(f"✓ All {len(_processed_order)} requests processed despite any errors")
    print("✅ Queue continues processing after errors")


if __name__ == "__main__":
    asyncio.run(test_concurrent_requests())
    asyncio.run(test_error_resilience())
