#!/usr/bin/env python3
"""
Test Client for SmolDocling RunPod Service
===========================================
Simple client to test the FastAPI service locally.
"""

import requests
import os
from pathlib import Path

def test_service():
    """Test the SmolDocling service with a sample PDF"""

    # Find a test PDF
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    test_pdfs_dir = project_root / "data" / "test_pdfs_for_vlm"

    pdf_files = list(test_pdfs_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No PDF files found in {test_pdfs_dir}")
        return

    pdf_path = pdf_files[0]
    print(f"📄 Testing with PDF: {pdf_path.name}")

    # Test health endpoint
    print("\n🔍 Testing health endpoint...")
    try:
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ Health check passed")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Could not connect to service: {e}")
        print("Make sure the service is running: uvicorn main:app --host 0.0.0.0 --port 8000")
        return

    # Test root endpoint
    print("\n🔍 Testing root endpoint...")
    try:
        response = requests.get("http://localhost:8000/")
        if response.status_code == 200:
            print("✅ Root endpoint working")
            print(f"   Service: {response.json().get('service', 'Unknown')}")
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Root endpoint error: {e}")

    # Test PDF processing
    print(f"\n🔍 Testing PDF processing with {pdf_path.name}...")
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            response = requests.post("http://localhost:8000/ocr", files=files)

        if response.status_code == 200:
            print("✅ PDF processing successful")

            # Save the zipfile
            output_zip = current_dir / f"{pdf_path.stem}_test_results.zip"
            with open(output_zip, 'wb') as f:
                f.write(response.content)
            print(f"💾 Saved results to: {output_zip}")

            # Check zipfile contents
            import zipfile
            with zipfile.ZipFile(output_zip, 'r') as zip_ref:
                contents = zip_ref.namelist()
                print(f"📦 Zipfile contents: {contents}")

        else:
            print(f"❌ PDF processing failed: {response.status_code}")
            print(f"   Error: {response.text}")

    except Exception as e:
        print(f"❌ PDF processing error: {e}")

    # Test placeholder endpoints
    print("\n🔍 Testing placeholder endpoints...")
    
    # Test serialize endpoint
    try:
        response = requests.post("http://localhost:8000/serialize")
        if response.status_code == 200:
            print("✅ Serialize endpoint working")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Serialize endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Serialize endpoint error: {e}")
    
    # Test chunk endpoint
    try:
        response = requests.post("http://localhost:8000/chunk")
        if response.status_code == 200:
            print("✅ Chunk endpoint working")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Chunk endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Chunk endpoint error: {e}")

    print("\n🎉 Test completed!")

if __name__ == "__main__":
    test_service()
