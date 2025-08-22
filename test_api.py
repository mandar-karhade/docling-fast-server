#!/usr/bin/env python3
"""
Simple API Test Script
======================
Test the FastAPI endpoints without requiring a PDF file.
"""

import requests
import json

def test_api_endpoints():
    """Test all API endpoints"""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Docling API endpoints...")
    
    # Test health endpoint
    print("\n1. Testing /health endpoint...")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            print("   ✅ Health endpoint working")
        else:
            print(f"   ❌ Health endpoint failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Health endpoint error: {e}")
    
    # Test serialize endpoint
    print("\n2. Testing /serialize endpoint...")
    try:
        response = requests.post(f"{base_url}/serialize")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            print("   ✅ Serialize endpoint working")
        else:
            print(f"   ❌ Serialize endpoint failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Serialize endpoint error: {e}")
    
    # Test chunk endpoint
    print("\n3. Testing /chunk endpoint...")
    try:
        response = requests.post(f"{base_url}/chunk")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            print("   ✅ Chunk endpoint working")
        else:
            print(f"   ❌ Chunk endpoint failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Chunk endpoint error: {e}")
    
    # Test OCR endpoint (without file - should return 422)
    print("\n4. Testing /ocr endpoint (without file)...")
    try:
        response = requests.post(f"{base_url}/ocr")
        print(f"   Status: {response.status_code}")
        if response.status_code == 422:
            print("   ✅ OCR endpoint correctly rejected request without file")
        else:
            print(f"   ❌ Unexpected response: {response.text}")
    except Exception as e:
        print(f"   ❌ OCR endpoint error: {e}")
    
    print("\n🎉 API test completed!")

if __name__ == "__main__":
    test_api_endpoints()
