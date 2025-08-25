#!/usr/bin/env python3
"""
Test script for multiple async OCR jobs
Submits multiple PDF files and tracks their status until completion
"""

import requests
import json
import time
import os
from pathlib import Path
from typing import Dict, List

# Configuration
API_BASE_URL = "http://localhost:8850"
TEST_PDF_DIR = Path("test_pdf")
POLL_INTERVAL = 15  # seconds between status checks
MAX_WAIT_TIME = 1800  # 30 minutes max wait time

def submit_async_job(pdf_path: Path) -> str:
    """Submit a PDF file for async processing and return job ID"""
    print(f"📤 Submitting {pdf_path.name}...")
    
    with open(pdf_path, 'rb') as f:
        files = {'file': (pdf_path.name, f, 'application/pdf')}
        response = requests.post(
            f"{API_BASE_URL}/ocr/async",
            files=files,
            headers={'Accept-Encoding': 'gzip'}
        )
    
    if response.status_code == 200:
        result = response.json()
        job_id = result['job_id']
        print(f"✅ Job submitted: {job_id}")
        return job_id
    else:
        print(f"❌ Failed to submit {pdf_path.name}: {response.status_code}")
        return None

def get_job_status(job_id: str) -> Dict:
    """Get the status of a specific job"""
    response = requests.get(f"{API_BASE_URL}/jobs/{job_id}")
    if response.status_code == 200:
        return response.json()
    else:
        return None

def get_all_jobs() -> List[Dict]:
    """Get list of all jobs"""
    response = requests.get(f"{API_BASE_URL}/jobs")
    if response.status_code == 200:
        return response.json()['jobs']
    else:
        return []

def is_job_complete(job_status: Dict) -> bool:
    """Check if a job is complete (success or failed)"""
    if not job_status or 'status' not in job_status:
        return False
    return job_status['status'] in ['completed', 'failed']

def print_job_summary(jobs: Dict[str, Dict], job_ids: List[str]):
    """Print a detailed summary of all jobs"""
    print("\n📊 Job Status Summary:")
    print("-" * 120)
    print(f"{'Job ID':<36} {'Worker':<8} {'Status':<12} {'Active':<6} {'Waiting':<8} {'Filename':<40}")
    print("-" * 120)
    
    for job_id in job_ids:
        if job_id in jobs:
            job = jobs[job_id]
            status = job.get('status', 'unknown')
            worker_num = job.get('uvicorn_worker_number', '?')
            active = job.get('active', False)
            waiting = job.get('waiting', True)
            filename = job.get('filename', 'Unknown')
            
            # Truncate filename if too long
            if len(filename) > 37:
                filename = filename[:34] + "..."
            
            # Status indicators
            if status == 'completed':
                status_display = '✅ COMPLETED'
            elif status == 'failed':
                status_display = '❌ FAILED'
            elif status == 'processing':
                status_display = '🔄 PROCESSING'
            elif status == 'waiting':
                status_display = '⏳ WAITING'
            else:
                status_display = f'❓ {status.upper()}'
            
            # Active/Waiting indicators
            active_display = '✅' if active else '❌'
            waiting_display = '⏳' if waiting else '✅'
            
            print(f"{job_id:<36} {worker_num:<8} {status_display:<12} {active_display:<6} {waiting_display:<8} {filename:<40}")
            
            # Show error if failed
            if status == 'failed':
                error = job.get('error', 'Unknown error')
                print(f"{'':<36} {'':<8} {'':<12} {'':<6} {'':<8} Error: {error}")
        else:
            print(f"{job_id:<36} {'?':<8} {'❓ NOT FOUND':<12} {'?':<6} {'?':<8} {'Unknown':<40}")
    
    print("-" * 120)

def main():
    """Main test function"""
    print("🚀 Starting multi-file async OCR test")
    print(f"📁 Looking for PDF files in: {TEST_PDF_DIR}")
    
    # Find all PDF files
    pdf_files = list(TEST_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No PDF files found in {TEST_PDF_DIR}")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files")
    
    # Submit all jobs
    job_ids = []
    for pdf_file in pdf_files:
        job_id = submit_async_job(pdf_file)
        if job_id:
            job_ids.append(job_id)
    
    if not job_ids:
        print("❌ No jobs were submitted successfully")
        return
    
    print(f"\n📋 Tracking {len(job_ids)} jobs...")
    
    # Track job status
    jobs = {}
    start_time = time.time()
    
    while True:
        # Check if we've exceeded max wait time
        if time.time() - start_time > MAX_WAIT_TIME:
            print(f"\n⏰ Timeout reached ({MAX_WAIT_TIME}s). Stopping tracking.")
            break
        
        # Get status of all jobs
        all_jobs = get_all_jobs()
        current_jobs = {}
        
        for job in all_jobs:
            job_id = job['job_id']
            if job_id in job_ids:
                current_jobs[job_id] = job
        
        # Update our tracking
        for job_id in job_ids:
            if job_id in current_jobs:
                jobs[job_id] = current_jobs[job_id]
        
        # Print current status
        print_job_summary(jobs, job_ids)
        
        # Count jobs by status
        status_counts = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'unknown': 0}
        for job_id in job_ids:
            if job_id in jobs:
                status = jobs[job_id].get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            else:
                status_counts['unknown'] += 1
        
        print(f"\n📈 Status Summary: {status_counts['pending']} pending, {status_counts['processing']} running, {status_counts['completed']} completed, {status_counts['failed']} failed")
        
        # Check if all jobs are complete
        all_complete = all(is_job_complete(jobs.get(job_id, {})) for job_id in job_ids)
        if all_complete:
            print("\n🎉 All jobs completed!")
            break
        
        # Wait before next check
        print(f"\n⏳ Waiting {POLL_INTERVAL}s before next check...")
        time.sleep(POLL_INTERVAL)
    
    # Final summary
    print("\n" + "="*80)
    print("📋 FINAL SUMMARY")
    print("="*80)
    
    completed_count = 0
    failed_count = 0
    processing_count = 0
    
    for job_id in job_ids:
        if job_id in jobs:
            job = jobs[job_id]
            status = job['status']
            filename = job.get('filename', 'Unknown')
            
            if status == 'completed':
                completed_count += 1
                print(f"✅ {filename}: SUCCESS")
            elif status == 'failed':
                failed_count += 1
                error = job.get('error', 'Unknown error')
                print(f"❌ {filename}: FAILED - {error}")
            else:
                processing_count += 1
                print(f"⏳ {filename}: {status} ({job.get('progress', 0)}%)")
        else:
            print(f"❓ {job_id}: NOT FOUND")
    
    print(f"\n📊 Results: {completed_count} completed, {failed_count} failed, {processing_count} still processing")

if __name__ == "__main__":
    main()
