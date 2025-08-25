#!/usr/bin/env python3
"""
Job Status Table Display
=======================
Display job status in a clean table format.
"""

import requests
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8850"

def get_jobs():
    """Get jobs from RQ system"""
    try:
        response = requests.get(f"{API_BASE_URL}/jobs")
        response.raise_for_status()
        return response.json().get('jobs', [])
    except Exception as e:
        print(f"❌ Failed to get jobs: {e}")
        return []

def get_queue_status():
    """Get RQ queue status"""
    try:
        response = requests.get(f"{API_BASE_URL}/queue_status")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Failed to get queue status: {e}")
        return {}

def format_timestamp(timestamp_str):
    """Format timestamp for display"""
    if not timestamp_str or timestamp_str == 'Unknown':
        return 'Unknown'
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%H:%M:%S')
    except:
        return timestamp_str

def main():
    """Display job status table"""
    print("📊 Job Status Table")
    print("=" * 140)
    
    # Get jobs from RQ system
    jobs = get_jobs()
    
    # Get RQ queue status
    queue_status = get_queue_status()
    queue_stats = queue_status.get('queue_stats', {})
    workers = queue_status.get('workers', [])
    
    # Create worker mapping
    worker_map = {}
    for worker in workers:
        current_job = worker.get('current_job', '')
        if current_job:
            worker_map[current_job] = worker.get('name', 'Unknown')
    
    # Print header
    print(f"{'JOB ID':<36} {'Created':<10} {'Started':<10} {'Status':<12} {'Worker':<15} {'Filename':<30}")
    print("-" * 140)
    
    # Display jobs
    for job in jobs:
        job_id = job.get('job_id', 'Unknown')[:35]
        created = format_timestamp(job.get('created_at', 'Unknown'))
        started = format_timestamp(job.get('started_at', 'Unknown'))
        status = job.get('status', 'Unknown')
        worker = worker_map.get(job_id, 'N/A')
        filename = job.get('filename', 'Unknown')
        
        # Truncate long filenames
        if len(filename) > 28:
            filename = filename[:25] + "..."
        
        print(f"{job_id:<36} {created:<10} {started:<10} {status:<12} {worker:<15} {filename:<30}")
    
    print("-" * 140)
    
    # Print summary
    print(f"\n📈 Summary:")
    print(f"   RQ jobs: {len(jobs)}")
    print(f"   RQ total jobs: {queue_stats.get('total_jobs', 0)}")
    print(f"   RQ workers: {queue_stats.get('workers', 0)}")
    print(f"   RQ failed jobs: {queue_stats.get('failed_jobs', 0)}")
    print(f"   RQ started jobs: {queue_stats.get('started_jobs', 0)}")
    
    print(f"\n🔧 Active Workers:")
    for worker in workers:
        state = worker.get('state', 'unknown')
        current_job = worker.get('current_job', 'None')
        print(f"   {worker.get('name', 'Unknown')}: {state} (job: {current_job})")
    
    # Status counts
    status_counts = {}
    for job in jobs:
        status = job.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"\n📊 Status Breakdown:")
    for status, count in status_counts.items():
        print(f"   {status}: {count}")

if __name__ == "__main__":
    main()
