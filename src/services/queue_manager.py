import os
import json
import psutil
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from upstash_redis import Redis
from rq import Queue

from src.models.job import Job, JobUpdate


class QueueManager:
    def __init__(self):
        # Use Upstash Redis REST API
        self.redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
        self.redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        if not self.redis_url or not self.redis_token:
            raise ValueError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required")
        
        # Create Upstash Redis client
        self.redis_conn = Redis(url=self.redis_url, token=self.redis_token)
        
        # Note: RQ doesn't work directly with Upstash Redis HTTP client
        # We'll need to handle async operations differently
        self.pdf_queue = None  # RQ queue not available with HTTP client
        
        # Job management with batch-based file persistence
        self.jobs_dir = os.getenv('JOBS_DIR', './jobs')
        self.current_batch_file = os.path.join(self.jobs_dir, 'current_batch.txt')
        self.jobs: Dict[str, Dict] = {}
        self._load_jobs()

    def _ensure_jobs_dir(self):
        """Ensure jobs directory exists"""
        os.makedirs(self.jobs_dir, exist_ok=True)

    def _get_current_batch_id(self) -> str:
        """Get current batch ID or create new one"""
        try:
            if os.path.exists(self.current_batch_file):
                with open(self.current_batch_file, 'r') as f:
                    return f.read().strip()
        except:
            pass
        
        # Create new batch ID
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            with open(self.current_batch_file, 'w') as f:
                f.write(batch_id)
        except Exception as e:
            print(f"❌ Error creating batch file: {e}")
        
        return batch_id

    def _get_jobs_file_path(self) -> str:
        """Get the current jobs file path"""
        batch_id = self._get_current_batch_id()
        return os.path.join(self.jobs_dir, f"jobs_{batch_id}.json")

    def _load_jobs(self):
        """Load jobs from current batch JSON file"""
        self._ensure_jobs_dir()
        jobs_file = self._get_jobs_file_path()
        
        try:
            if os.path.exists(jobs_file):
                with open(jobs_file, 'r') as f:
                    self.jobs = json.load(f)
        except Exception as e:
            print(f"❌ Error loading jobs from {jobs_file}: {e}")
            self.jobs = {}

    def _save_jobs(self):
        """Save jobs to current batch JSON file"""
        self._ensure_jobs_dir()
        jobs_file = self._get_jobs_file_path()
        
        try:
            # Create a simplified version for storage (remove large objects)
            storage_jobs = {}
            for job_id, job in self.jobs.items():
                storage_job = job.copy()
                # Remove large objects that can cause JSON issues
                if 'result' in storage_job and storage_job['result']:
                    result = storage_job['result'].copy()
                    if 'files' in result and 'converted_doc' in result['files']:
                        result['files']['converted_doc'] = '<removed_large_object>'
                    storage_job['result'] = result
                storage_jobs[job_id] = storage_job
            
            with open(jobs_file, 'w') as f:
                json.dump(storage_jobs, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving jobs to {jobs_file}: {e}")

    def create_new_batch(self) -> str:
        """Create a new batch and return batch ID"""
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            with open(self.current_batch_file, 'w') as f:
                f.write(batch_id)
            print(f"🆕 Created new batch: {batch_id}")
            return batch_id
        except Exception as e:
            print(f"❌ Error creating new batch: {e}")
            return batch_id

    def get_worker_info(self) -> Dict:
        """Get current worker process information"""
        pid = os.getpid()
        process = psutil.Process(pid)
        
        # Try to determine worker number from parent process
        try:
            parent = process.parent()
            if parent:
                # Uvicorn workers are typically children of the main process
                # Worker numbers are usually assigned in order of creation
                worker_number = pid % 1000  # Simple way to get a worker number
            else:
                worker_number = 1
        except:
            worker_number = 1
        
        return {
            "worker_id": pid,
            "worker_number": worker_number,
            "worker_name": f"worker-{worker_number}",
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "num_threads": process.num_threads(),
            "status": process.status()
        }

    def get_worker_queue_info(self) -> Dict:
        """Get information about current worker's queue"""
        try:
            # Get current worker's async tasks
            loop = asyncio.get_event_loop()
            tasks = asyncio.all_tasks(loop)
            
            # Filter for our PDF processing tasks
            pdf_tasks = [task for task in tasks if task.get_name().startswith('process_pdf_')]
            
            return {
                "total_tasks": len(tasks),
                "pdf_processing_tasks": len(pdf_tasks),
                "task_names": [task.get_name() for task in pdf_tasks],
                "task_statuses": [task._state for task in pdf_tasks]
            }
        except Exception as e:
            return {"error": str(e)}

    def create_job(self) -> str:
        """Create a new job and return job ID"""
        import uuid
        job_id = str(uuid.uuid4())
        worker_info = self.get_worker_info()
        
        self.jobs[job_id] = {
            "id": job_id,
            "status": "waiting",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "uvicorn_worker_number": worker_info["worker_number"],
            "active": False,
            "waiting": True,
            "result": None,
            "error": None,
            "logs": [],
            "worker_info": worker_info
        }
        
        # Add initial log entry
        self.jobs[job_id]["logs"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Job created and assigned to {worker_info['worker_name']} (PID: {worker_info['worker_id']})"
        })
        
        self._save_jobs()
        print(f"✅ Created job {job_id} on {worker_info['worker_name']}")
        return job_id

    def update_job(self, job_id: str, update: JobUpdate, log_message: Optional[str] = None):
        """Update job status and information"""
        if job_id in self.jobs:
            if update.status is not None:
                self.jobs[job_id]["status"] = update.status
            if update.result is not None:
                self.jobs[job_id]["result"] = update.result
            if update.error is not None:
                self.jobs[job_id]["error"] = update.error
            if update.active is not None:
                self.jobs[job_id]["active"] = update.active
            if update.waiting is not None:
                self.jobs[job_id]["waiting"] = update.waiting
            if update.rq_job_id is not None:
                self.jobs[job_id]["rq_job_id"] = update.rq_job_id
                
            self.jobs[job_id]["updated_at"] = datetime.utcnow().isoformat()
            
            if log_message is not None:
                self.jobs[job_id]["logs"].append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": log_message
                })
                
            self._save_jobs()
            print(f"🔧 Updated job {job_id}: status={update.status}, active={update.active}, waiting={update.waiting}")
        else:
            print(f"❌ Job {job_id} not found in jobs dictionary")

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs()
            return True
        return False

    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs"""
        return self.jobs

    def get_queue_status(self) -> Dict:
        """Get RQ queue status and statistics"""
        try:
            # Get queue statistics
            queue_stats = {
                "queue_name": "pdf_processing",
                "total_jobs": len(self.pdf_queue),
                "workers": len(self.pdf_queue.connection.smembers('rq:workers')),
                "failed_jobs": len(self.pdf_queue.failed_job_registry),
                "started_jobs": len(self.pdf_queue.started_job_registry),
                "deferred_jobs": len(self.pdf_queue.deferred_job_registry),
                "scheduled_jobs": len(self.pdf_queue.scheduled_job_registry),
            }
            
            # Get worker information
            workers = []
            try:
                worker_names = self.pdf_queue.connection.smembers('rq:workers')
                for worker_name in worker_names:
                    worker_name_str = worker_name.decode()
                    workers.append({
                        "name": worker_name_str,
                        "state": "active",
                        "current_job": "",
                        "last_heartbeat": ""
                    })
            except Exception as e:
                print(f"Error getting worker info: {e}")
                workers = []
            
            # Get recent jobs
            recent_jobs = []
            for job in self.pdf_queue.get_jobs()[:10]:  # Last 10 jobs
                recent_jobs.append({
                    "job_id": job.id,
                    "status": job.get_status(),
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                    "result": str(job.result)[:100] + "..." if job.result and len(str(job.result)) > 100 else job.result,
                    "exc_info": job.exc_info,
                    "filename": job.meta.get('filename', 'Unknown') if job.meta else 'Unknown'
                })
            
            return {
                "status": "success",
                "queue_stats": queue_stats,
                "workers": workers,
                "recent_jobs": recent_jobs,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to get queue status"
            }

    def get_rq_job(self, job_id: str):
        """Get RQ job by ID"""
        return self.pdf_queue.fetch_job(job_id)

    def enqueue_job(self, func, *args, **kwargs):
        """Enqueue a job to RQ"""
        return self.pdf_queue.enqueue(func, *args, **kwargs)


# Global queue manager instance
queue_manager = QueueManager()
