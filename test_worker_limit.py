#!/usr/bin/env python3
"""
Quick test to verify RQ_WORKERS=2 limit is respected
"""

import requests
import time
from pathlib import Path

API_BASE_URL = "http://localhost:8850"

def test_worker_limit():
    print("🧪 Testing RQ_WORKERS=2 limit with 5 PDFs")
    print("=" * 50)
    
    # Get first 5 PDF files
    test_pdfs = sorted(list(Path("test_pdf").glob("*.pdf")))[:5]
    
    # Submit all 5 jobs quickly
    job_ids = []
    for pdf in test_pdfs:
        with open(pdf, 'rb') as f:
            files = {'file': (pdf.name, f, 'application/pdf')}
            response = requests.post(f"{API_BASE_URL}/ocr/async", files=files, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            job_ids.append((pdf.name, job_id))
            print(f"✅ Submitted {pdf.name}: {job_id}")
    
    print(f"\n📊 Submitted {len(job_ids)} jobs, checking worker activity...")
    
    # Check queue status immediately after submission
    for i in range(3):
        time.sleep(2)
        try:
            response = requests.get(f"{API_BASE_URL}/queue_status")
            if response.status_code == 200:
                status = response.json()
                stats = status.get('queue_stats', {})
                
                print(f"⏰ Check {i+1}:")
                print(f"   Max Workers: {stats.get('max_workers', 'unknown')}")
                print(f"   Active Workers: {stats.get('active_workers', 'unknown')}")
                print(f"   Processing Jobs: {stats.get('processing_jobs', 'unknown')}")
                print(f"   Queued Jobs: {stats.get('queued_jobs', 'unknown')}")
                
                # The key test: processing_jobs should never exceed max_workers (2)
                processing = stats.get('processing_jobs', 0)
                max_workers = stats.get('max_workers', 2)
                
                if processing > max_workers:
                    print(f"❌ FAIL: {processing} jobs processing > {max_workers} max workers!")
                else:
                    print(f"✅ PASS: {processing} jobs processing ≤ {max_workers} max workers")
        except Exception as e:
            print(f"⚠️ Error checking status: {e}")

if __name__ == "__main__":
    test_worker_limit()
