#!/usr/bin/env python3
"""
Test RunPod OCR with Small PDF
==============================
Test the OCR endpoint on RunPod with the smallest PDF file.
"""

import requests
import json
import os
from pathlib import Path

def test_runpod_small_ocr():
    """Test the OCR endpoint on RunPod with the smallest PDF file"""
    base_url = "https://bzyk0ttlxaq3gx-8000.proxy.runpod.net"  # RunPod URL
    
    # Find the smallest PDF
    test_pdf_dir = Path("test_pdf")
    pdf_files = list(test_pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in test_pdf directory")
        return
    
    # Use the smallest PDF (154KB)
    smallest_pdf = min(pdf_files, key=lambda x: x.stat().st_size)
    pdf_path = smallest_pdf
    print(f"📄 Testing RunPod OCR with smallest PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024:.1f} KB)")
    print(f"🌐 RunPod endpoint: {base_url}")
    
    # Test health first
    print(f"\n🔍 Testing health endpoint...")
    try:
        health_response = requests.get(f"{base_url}/health", timeout=30)
        print(f"   Health Status: {health_response.status_code}")
        if health_response.status_code == 200:
            print(f"   Health Response: {health_response.json()}")
        else:
            print(f"   Health Error: {health_response.text}")
    except Exception as e:
        print(f"   Health check failed: {e}")
    
    # Test OCR endpoint with PDF file
    print(f"\n🔍 Testing RunPod OCR endpoint with {pdf_path.name}...")
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            headers = {
                'Accept-Encoding': 'gzip, deflate, br'  # Request compression
            }
            
            print("📤 Uploading PDF to RunPod server...")
            response = requests.post(f"{base_url}/ocr", files=files, headers=headers, timeout=3600)

        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ RunPod OCR processing successful!")
            
            # Parse JSON response
            result = response.json()
            print(f"📄 Processed file: {result['filename']}")
            
            # Save individual files
            files = result['files']
            for file_type, content in files.items():
                if file_type == 'converted_doc':
                    # Skip the converted_doc object as it's not a string
                    print(f"📄 {file_type}: Document object (not saved to file)")
                elif file_type == 'json':
                    # JSON is already a dict, convert to string
                    content_str = json.dumps(content, indent=2)
                    output_file = Path(f"output/runpod_small_{pdf_path.stem}.{file_type}")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content_str)
                    print(f"💾 Saved {file_type}: {output_file} ({len(content_str) / 1024:.1f} KB)")
                else:
                    # Other formats are already strings
                    output_file = Path(f"output/runpod_small_{pdf_path.stem}.{file_type}")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"💾 Saved {file_type}: {output_file} ({len(content) / 1024:.1f} KB)")
            
            # Show total response size
            response_size = len(response.content) / 1024
            print(f"📊 Total response size: {response_size:.1f} KB")
            
            # Check if response was compressed
            if 'content-encoding' in response.headers:
                print(f"🗜️ Response was compressed with: {response.headers['content-encoding']}")
                # Calculate compression ratio
                uncompressed_size = int(response.headers.get('content-length', 0)) / 1024
                if uncompressed_size > 0:
                    compression_ratio = (1 - response_size / uncompressed_size) * 100
                    print(f"📉 Compression ratio: {compression_ratio:.1f}%")
            else:
                print("📦 Response was not compressed")

        else:
            print(f"❌ RunPod OCR processing failed: {response.status_code}")
            print(f"   Error: {response.text}")

    except requests.exceptions.Timeout:
        print("⏰ Request timed out - OCR processing took too long")
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error - Check if the RunPod server is accessible")
    except Exception as e:
        print(f"❌ RunPod OCR processing error: {e}")
        import traceback
        traceback.print_exc()

    print("\n🎉 RunPod small PDF OCR test completed!")

if __name__ == "__main__":
    test_runpod_small_ocr()
