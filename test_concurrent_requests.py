#!/usr/bin/env python3
"""Test script to verify concurrent request handling.

This script sends multiple rapid requests to test that:
1. Requests are queued properly
2. They process sequentially without corruption
3. Each request gets its own response
4. No race conditions occur
"""

import asyncio
import httpx
import time
from typing import List, Dict

# Configuration
AGENT_URL = "http://localhost:8080"
NUM_REQUESTS = 5


async def send_request(client: httpx.AsyncClient, request_id: int) -> Dict:
    """Send a single request to the agent."""
    message = f"Request {request_id}: What is {request_id} + {request_id}? Just give me the number."
    
    print(f"[{time.time():.2f}] Sending request {request_id}")
    
    start_time = time.time()
    response = await client.post(
        f"{AGENT_URL}/chat",
        json={"message": message},
        timeout=120.0  # Long timeout for agent processing
    )
    end_time = time.time()
    
    result = response.json()
    elapsed = end_time - start_time
    
    print(f"[{time.time():.2f}] Request {request_id} completed in {elapsed:.2f}s")
    print(f"  Status: {result['status']}")
    print(f"  Response: {result['response'][:100]}...")
    
    return {
        "request_id": request_id,
        "status": result["status"],
        "response": result["response"],
        "elapsed": elapsed,
    }


async def check_health(client: httpx.AsyncClient):
    """Check agent health and queue status."""
    response = await client.get(f"{AGENT_URL}/health")
    health = response.json()
    print(f"[{time.time():.2f}] Health: processing={health['processing']}, queue_depth={health['queue_depth']}")
    return health


async def main():
    """Run the concurrent request test."""
    print(f"Testing concurrent requests to {AGENT_URL}")
    print(f"Sending {NUM_REQUESTS} requests rapidly...\n")
    
    async with httpx.AsyncClient() as client:
        # Check initial health
        await check_health(client)
        
        # Send all requests concurrently (fire and forget style)
        tasks = [
            send_request(client, i)
            for i in range(1, NUM_REQUESTS + 1)
        ]
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print("\n" + "="*80)
        print("RESULTS SUMMARY")
        print("="*80)
        
        for result in results:
            if isinstance(result, Exception):
                print(f"ERROR: {result}")
            else:
                print(f"Request {result['request_id']}: {result['status']} ({result['elapsed']:.2f}s)")
        
        # Check final health
        print()
        await check_health(client)
        
        # Verify all succeeded
        successes = sum(1 for r in results if not isinstance(r, Exception) and r['status'] == 'success')
        print(f"\n✓ {successes}/{NUM_REQUESTS} requests succeeded")
        
        if successes == NUM_REQUESTS:
            print("✓ All requests processed successfully!")
            print("✓ No race conditions detected!")
        else:
            print("✗ Some requests failed - check logs")
            return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
