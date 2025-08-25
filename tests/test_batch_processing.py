#!/usr/bin/env python3
"""
Batch PDF Processing Script
==========================
Process all PDFs in test_pdf directory using the RQ-based API
and save results to output directory.
"""

import os
import time
import json
import requests
from pathlib import Path
from datetime import datetime
import gzip
import base64

# Configuration
API_BASE_URL = "http://localhost:8850"
TEST_PDF_DIR = Path("test_pdf")
OUTPUT_DIR = Path("output")
POLL_INTERVAL = 60  # seconds between status checks (1 minute)
MAX_WAIT_TIME = 3600  # 1 hour max wait time

def ensure_output_dir():
    """Ensure output directory exists"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"📁 Output directory: {OUTPUT_DIR.absolute()}")

def submit_pdf_job(pdf_path: Path) -> str:
    """Submit a PDF for processing and return job ID"""
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            response = requests.post(f"{API_BASE_URL}/ocr/async", files=files)
            response.raise_for_status()
            
        result = response.json()
        job_id = result['job_id']
        print(f"📤 Submitted {pdf_path.name} → Job ID: {job_id}")
        return job_id
        
    except Exception as e:
        print(f"❌ Failed to submit {pdf_path.name}: {e}")
        return None

def get_queue_status() -> dict:
    """Get RQ queue status"""
    try:
        response = requests.get(f"{API_BASE_URL}/queue_status")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Failed to get queue status: {e}")
        return {}

def get_job_status(job_id: str) -> dict:
    """Get status of a specific job from RQ"""
    try:
        # First try to get from RQ queue
        queue_status = get_queue_status()
        recent_jobs = queue_status.get('recent_jobs', [])
        
        for job in recent_jobs:
            if job['job_id'] == job_id:
                return {
                    'job_id': job_id,
                    'status': job['status'],
                    'created_at': job['created_at'],
                    'started_at': job['started_at'],
                    'ended_at': job['ended_at'],
                    'result': job['result'],
                    'error': job.get('exc_info')
                }
        
        # If not found in recent jobs, check if it's completed
        # We'll need to check the file-based system for completed jobs
        response = requests.get(f"{API_BASE_URL}/jobs/{job_id}")
        if response.status_code == 200:
            return response.json()
        
        return {'job_id': job_id, 'status': 'not_found'}
        
    except Exception as e:
        print(f"❌ Failed to get status for job {job_id}: {e}")
        return {'job_id': job_id, 'status': 'error'}

def get_all_jobs() -> list:
    """Get all jobs from RQ queue"""
    try:
        queue_status = get_queue_status()
        return queue_status.get('recent_jobs', [])
    except Exception as e:
        print(f"❌ Failed to get jobs: {e}")
        return []

def is_job_complete(job_status: dict) -> bool:
    """Check if job is completed or failed"""
    status = job_status.get('status', 'unknown')
    return status in ['completed', 'failed', 'finished']

def download_job_result(job_id: str, filename: str) -> bool:
    """Download completed job result"""
    try:
        # Get job status to check if it's completed
        job_status = get_job_status(job_id)
        if job_status.get('status') != 'completed':
            print(f"⚠️  Job {job_id} not completed yet")
            return False
            
        result = job_status.get('result', {})
        if not result:
            print(f"⚠️  No result found for job {job_id}")
            return False
            
        # Create output file path
        output_file = OUTPUT_DIR / f"{filename}_results.json.gz"
        
        # Save the complete result
        with gzip.open(output_file, 'wt', encoding='utf-8') as f:
            json.dump({
                'job_id': job_id,
                'filename': filename,
                'status': 'completed',
                'timestamp': datetime.utcnow().isoformat(),
                'result': result
            }, f, indent=2)
            
        print(f"💾 Saved results for {filename} → {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download result for job {job_id}: {e}")
        return False

def print_job_summary(jobs: dict, job_ids: list):
    """Print a formatted summary of job statuses"""
    print("\n📊 Job Status Summary:")
    print("-" * 100)
    print(f"{'Job ID':<36} {'Status':<12} {'Created':<20} {'Started':<20} {'Filename':<20}")
    print("-" * 100)
    
    for job_id in job_ids:
        job = jobs.get(job_id, {})
        status = job.get('status', '❓ NOT FOUND')
        created_at = job.get('created_at', 'Unknown')
        started_at = job.get('started_at', 'Not started')
        filename = job.get('filename', 'Unknown')
        
        # Truncate timestamps
        if created_at and created_at != 'Unknown':
            created_at = created_at.split('T')[1][:8]  # Just time part
        else:
            created_at = 'Unknown'
        if started_at and started_at != 'Not started':
            started_at = started_at.split('T')[1][:8]  # Just time part
        else:
            started_at = 'Not started'
        
        # Truncate long filenames
        if len(filename) > 18:
            filename = filename[:15] + "..."
        
        print(f"{job_id:<36} {status:<12} {created_at:<20} {started_at:<20} {filename:<20}")
    
    print("-" * 100)
    
    # Print status summary
    status_counts = {'queued': 0, 'started': 0, 'finished': 0, 'failed': 0, 'completed': 0}
    for job in jobs.values():
        status = job.get('status', 'unknown')
        if status in status_counts:
            status_counts[status] += 1
    
    print(f"📈 Status Summary: {status_counts['queued']} queued, {status_counts['started']} started, {status_counts['finished']} finished, {status_counts['completed']} completed, {status_counts['failed']} failed")

def main():
    """Main batch processing function"""
    print("🚀 Starting batch PDF processing")
    print(f"📁 Looking for PDF files in: {TEST_PDF_DIR}")
    print(f"💾 Results will be saved to: {OUTPUT_DIR}")
    
    # Ensure output directory exists
    ensure_output_dir()
    
    # Find all PDF files
    pdf_files = list(TEST_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No PDF files found in {TEST_PDF_DIR}")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files")
    
    # Submit all jobs
    job_ids = []
    filename_map = {}  # Map job_id to filename
    
    for pdf_file in pdf_files:
        job_id = submit_pdf_job(pdf_file)
        if job_id:
            job_ids.append(job_id)
            filename_map[job_id] = pdf_file.stem
    
    if not job_ids:
        print("❌ No jobs were submitted successfully")
        return
    
    print(f"\n📋 Tracking {len(job_ids)} jobs...")
    
    # Track job status
    jobs = {}
    start_time = time.time()
    completed_jobs = set()
    
    while True:
        # Check if we've exceeded max wait time
        if time.time() - start_time > MAX_WAIT_TIME:
            print(f"\n⏰ Timeout reached ({MAX_WAIT_TIME}s). Stopping tracking.")
            break
        
        # Get status of all jobs from RQ
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
            else:
                # Check if job is completed in file-based system
                job_status = get_job_status(job_id)
                if job_status.get('status') != 'not_found':
                    jobs[job_id] = job_status
        
        # Print current status
        print_job_summary(jobs, job_ids)
        
        # Check for newly completed jobs and download results
        for job_id in job_ids:
            if job_id in jobs and job_id not in completed_jobs:
                job_status = jobs[job_id]
                if is_job_complete(job_status):
                    filename = filename_map.get(job_id, job_id)
                    if download_job_result(job_id, filename):
                        completed_jobs.add(job_id)
        
        # Check if all jobs are complete
        all_complete = all(is_job_complete(jobs.get(job_id, {})) for job_id in job_ids)
        if all_complete:
            print("\n🎉 All jobs completed!")
            break
        
        print(f"\n⏳ Waiting {POLL_INTERVAL}s before next check...")
        time.sleep(POLL_INTERVAL)
    
    # Final summary
    print("\n📋 Final Summary:")
    print(f"✅ Completed jobs: {len(completed_jobs)}")
    print(f"📁 Results saved to: {OUTPUT_DIR.absolute()}")
    
    # List saved files
    saved_files = list(OUTPUT_DIR.glob("*.json.gz"))
    if saved_files:
        print("\n💾 Saved result files:")
        for file in saved_files:
            print(f"   {file.name}")

if __name__ == "__main__":
    main()
