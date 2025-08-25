#!/usr/bin/env python3
"""
Test RunPod Async OCR with Polling
==================================
Test the async OCR endpoint on RunPod with polling for job status.
"""

import requests
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

def test_runpod_async_ocr():
    """Test the async OCR endpoint on RunPod with polling"""
    # Get RunPod URL from environment variable
    runpod_machine_id = os.getenv('RUNPOD_MACHINE_ID')
    if not runpod_machine_id:
        print("❌ Error: RUNPOD_MACHINE_ID environment variable not set")
        print("   Please set it to your RunPod machine ID (e.g., 'g2zuausy1g8sj2-8000')")
        return
    
    base_url = f"https://{runpod_machine_id}-8000.proxy.runpod.net"
    
    # Find the largest PDF for testing
    test_pdf_dir = Path("test_pdf")
    pdf_files = list(test_pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in test_pdf directory")
        return
    
    # Use the largest PDF for testing async processing
    largest_pdf = max(pdf_files, key=lambda x: x.stat().st_size)
    pdf_path = largest_pdf
    print(f"📄 Testing RunPod Async OCR with largest PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024:.1f} KB)")
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
        return
    
    # Start async OCR processing
    print(f"\n🚀 Starting async OCR processing for {pdf_path.name}...")
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            headers = {
                'Accept-Encoding': 'gzip, deflate, br'
            }
            
            print("📤 Uploading PDF to RunPod server...")
            response = requests.post(f"{base_url}/ocr/async", files=files, headers=headers, timeout=30)

        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            job_id = result['job_id']
            print(f"✅ Async job started successfully!")
            print(f"   Job ID: {job_id}")
            print(f"   Status: {result['status']}")
            print(f"   Message: {result['message']}")
            
            # Poll for job completion
            print(f"\n⏳ Polling for job completion...")
            max_polls = 60  # Maximum 10 minutes (60 * 10 seconds)
            poll_interval = 10  # Poll every 10 seconds
            
            for poll_count in range(max_polls):
                try:
                    status_response = requests.get(f"{base_url}/jobs/{job_id}", timeout=30)
                    
                    if status_response.status_code == 200:
                        job_status = status_response.json()
                        status = job_status['status']
                        progress = job_status['progress']
                        
                        print(f"   Poll {poll_count + 1}: Status={status}, Progress={progress}%")
                        
                        if status == 'completed':
                            print(f"✅ Job completed successfully!")
                            
                            # Save results
                            result_data = job_status['result']
                            if result_data and 'files' in result_data:
                                files = result_data['files']
                                for file_type, content in files.items():
                                    if file_type == 'converted_doc':
                                        print(f"📄 {file_type}: Document object (not saved to file)")
                                    elif file_type == 'json':
                                        content_str = json.dumps(content, indent=2)
                                        output_file = Path(f"output/runpod_async_{pdf_path.stem}.{file_type}")
                                        with open(output_file, 'w', encoding='utf-8') as f:
                                            f.write(content_str)
                                        print(f"💾 Saved {file_type}: {output_file} ({len(content_str) / 1024:.1f} KB)")
                                    else:
                                        output_file = Path(f"output/runpod_async_{pdf_path.stem}.{file_type}")
                                        with open(output_file, 'w', encoding='utf-8') as f:
                                            f.write(content)
                                        print(f"💾 Saved {file_type}: {output_file} ({len(content) / 1024:.1f} KB)")
                            
                            return
                            
                        elif status == 'failed':
                            error = job_status.get('error', 'Unknown error')
                            print(f"❌ Job failed: {error}")
                            return
                            
                        elif status in ['pending', 'processing']:
                            # Continue polling
                            time.sleep(poll_interval)
                            continue
                            
                    else:
                        print(f"   Poll {poll_count + 1}: Error getting status - {status_response.status_code}")
                        time.sleep(poll_interval)
                        
                except Exception as e:
                    print(f"   Poll {poll_count + 1}: Exception - {e}")
                    time.sleep(poll_interval)
            
            print(f"⏰ Polling timeout reached. Job may still be processing.")
            
        else:
            print(f"❌ Failed to start async job: {response.status_code}")
            print(f"   Error: {response.text}")

    except requests.exceptions.Timeout:
        print("⏰ Request timed out - Failed to start async job")
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error - Check if the RunPod server is accessible")
    except Exception as e:
        print(f"❌ Async OCR processing error: {e}")
        import traceback
        traceback.print_exc()

    print("\n🎉 RunPod async OCR test completed!")

if __name__ == "__main__":
    test_runpod_async_ocr()
