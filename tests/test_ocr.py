#!/usr/bin/env python3
"""
Test OCR Endpoint with PDF File
===============================
Test the /ocr endpoint with an actual PDF file to verify the full pipeline.
"""

import requests
import json
import os
from pathlib import Path

def test_ocr_with_pdf():
    """Test the OCR endpoint with a real PDF file"""
    base_url = "http://localhost:8000"
    
    # Find a test PDF
    test_pdf_dir = Path("test_pdf")
    pdf_files = list(test_pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in test_pdf directory")
        return
    
    # Use the smaller PDF for testing
    pdf_path = pdf_files[0]  # First PDF file
    print(f"📄 Testing OCR with PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024:.1f} KB)")
    
    # Test OCR endpoint with PDF file
    print(f"\n🔍 Testing OCR endpoint with {pdf_path.name}...")
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            headers = {
                'Accept-Encoding': 'gzip, deflate, br'  # Request compression
            }
            response = requests.post(f"{base_url}/ocr", files=files, headers=headers)

        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ OCR processing successful!")
            
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
                    output_file = Path(f"output/{pdf_path.stem}.{file_type}")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content_str)
                    print(f"💾 Saved {file_type}: {output_file} ({len(content_str) / 1024:.1f} KB)")
                else:
                    # Other formats are already strings
                    output_file = Path(f"output/{pdf_path.stem}.{file_type}")
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
            print(f"❌ OCR processing failed: {response.status_code}")
            print(f"   Error: {response.text}")

    except Exception as e:
        print(f"❌ OCR processing error: {e}")
        import traceback
        traceback.print_exc()

    print("\n🎉 OCR test completed!")

if __name__ == "__main__":
    test_ocr_with_pdf()
