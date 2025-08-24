#!/usr/bin/env python3

from upstash_redis import Redis

# Redis configuration
REDIS_REST_URL = "https://primary-tarpon-42548.upstash.io"
REDIS_REST_TOKEN = "AaY0AAIncDE4ZmQzN2Y3NzQ0Y2I0ZTIzYWY3YzgwNzE5NWJlNzgyZHAxNDI1NDg"

print("Testing Upstash Redis connection...")
print(f"REST URL: {REDIS_REST_URL}")
print(f"Token: {REDIS_REST_TOKEN[:20]}...")

try:
    # Test Upstash Redis connection
    print("\n1. Testing Upstash Redis connection...")
    r = Redis(url=REDIS_REST_URL, token=REDIS_REST_TOKEN)
    result = r.ping()
    print(f"✅ Upstash Redis connection successful: {result}")
    
    # Test basic operations
    print("\n2. Testing basic operations...")
    r.set("test_key", "test_value")
    value = r.get("test_key")
    print(f"✅ Set/Get operation successful: {value}")
    
    # Clean up
    r.delete("test_key")
    print("✅ Delete operation successful")
    
except Exception as e:
    print(f"❌ Upstash Redis connection failed: {e}")
    print(f"Error type: {type(e).__name__}")

print("\nUpstash Redis connection test completed.")
