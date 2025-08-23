from fastapi import APIRouter, HTTPException
from datetime import datetime

from src.services.queue_manager import queue_manager
from src.models.job import JobUpdate

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results using RQ job ID"""
    try:
        # Get job from RQ
        rq_job = queue_manager.get_rq_job(job_id)
        if not rq_job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Get job status
        status = rq_job.get_status()
        
        # Get result if job is finished
        result = None
        error = None
        if status == 'finished':
            try:
                result = rq_job.result
            except Exception as e:
                error = str(e)
        elif status == 'failed':
            error = str(rq_job.exc_info) if rq_job.exc_info else "Unknown error"
        
        return {
            "job_id": job_id,
            "status": status,
            "created_at": rq_job.created_at.isoformat() if rq_job.created_at else None,
            "started_at": rq_job.started_at.isoformat() if rq_job.started_at else None,
            "ended_at": rq_job.ended_at.isoformat() if rq_job.ended_at else None,
            "result": result,
            "error": error,
            "filename": rq_job.meta.get('filename', 'Unknown') if rq_job.meta else 'Unknown'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting job status: {str(e)}")


@router.get("/jobs")
async def list_jobs():
    """List all RQ jobs"""
    try:
        # Get all jobs from RQ queue
        rq_jobs = queue_manager.pdf_queue.get_jobs()
        
        jobs_list = []
        for rq_job in rq_jobs:
            jobs_list.append({
                "job_id": rq_job.id,
                "status": rq_job.get_status(),
                "created_at": rq_job.created_at.isoformat() if rq_job.created_at else None,
                "started_at": rq_job.started_at.isoformat() if rq_job.started_at else None,
                "ended_at": rq_job.ended_at.isoformat() if rq_job.ended_at else None,
                "filename": rq_job.meta.get('filename', 'Unknown') if rq_job.meta else 'Unknown'
            })
        
        return {"jobs": jobs_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing jobs: {str(e)}")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job"""
    if queue_manager.delete_job(job_id):
        return {"status": "deleted", "job_id": job_id}
    else:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/get_logs")
async def get_logs():
    """Get the latest log file content"""
    try:
        # Get current batch ID
        batch_id = queue_manager._get_current_batch_id()
        jobs_file = queue_manager._get_jobs_file_path()
        
        # Check if jobs file exists
        import os
        if not os.path.exists(jobs_file):
            return {
                "status": "no_logs",
                "batch_id": batch_id,
                "message": "No jobs file found for current batch"
            }
        
        # Read the jobs file
        import json
        with open(jobs_file, 'r') as f:
            jobs_data = json.load(f)
        
        # Count jobs by status
        status_counts = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}
        for job in jobs_data.values():
            status = job.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Get latest logs from all jobs
        all_logs = []
        for job_id, job in jobs_data.items():
            logs = job.get('logs', [])
            for log in logs:
                log['job_id'] = job_id
                log['filename'] = job.get('filename', 'Unknown')
                all_logs.append(log)
        
        # Sort logs by timestamp
        all_logs.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            "status": "success",
            "batch_id": batch_id,
            "jobs_file": jobs_file,
            "status_summary": status_counts,
            "total_jobs": len(jobs_data),
            "total_logs": len(all_logs),
            "latest_logs": all_logs[-20:] if all_logs else [],  # Last 20 logs
            "jobs_data": jobs_data
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to retrieve logs"
        }


@router.get("/worker_status")
async def get_worker_status():
    """Get current worker status and queue information"""
    try:
        worker_info = queue_manager.get_worker_info()
        queue_info = queue_manager.get_worker_queue_info()
        
        return {
            "status": "success",
            "worker_info": worker_info,
            "queue_info": queue_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get worker status"
        }


@router.get("/queue_status")
async def get_queue_status():
    """Get RQ queue status and statistics"""
    print("QUEUE_STATUS_ENDPOINT_CALLED")
    try:
        print("Starting queue_status endpoint")
        
        queue_status = queue_manager.get_queue_status()
        print(f"Returning response with {len(queue_status.get('workers', []))} workers")
        return queue_status
    except Exception as e:
        print(f"Exception in queue_status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get queue status"
        }
