import os
import psutil
import asyncio
import queue
import threading
import json
import fcntl
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from upstash_redis import Redis

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
        
        # Worker pool configuration
        self.max_workers = int(os.getenv('RQ_WORKERS', 2))
        print(f"🔧 Queue Manager: Using {self.max_workers} workers (from RQ_WORKERS)")
        
        # Create worker pool that respects RQ_WORKERS limit
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="pdf_worker"
        )
        
        # Job management (shared file storage for multi-worker compatibility)  
        self.jobs_file = Path("/tmp/docling_jobs.json")
        self._ensure_jobs_file()
        self.jobs: Dict[str, Dict] = {}
        
        # Track active workers
        self.active_workers = 0
        self.worker_lock = threading.Lock()
        
        # File lock for shared storage
        self.file_lock = threading.Lock()

    def _ensure_jobs_file(self):
        """Ensure the jobs file exists"""
        if not self.jobs_file.exists():
            with open(self.jobs_file, 'w') as f:
                json.dump({}, f)
    
    def _load_jobs_from_file(self) -> Dict[str, Dict]:
        """Load jobs from shared file storage"""
        try:
            with open(self.jobs_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                jobs_data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Unlock
                return jobs_data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_jobs_to_file(self, jobs_data: Dict[str, Dict]):
        """Save jobs to shared file storage"""
        try:
            with open(self.jobs_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
                json.dump(jobs_data, f, indent=2)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Unlock
        except Exception as e:
            print(f"⚠️ Error saving jobs to file: {e}")
    
    def _sync_jobs(self):
        """Sync in-memory jobs with file storage"""
        with self.file_lock:
            self.jobs = self._load_jobs_from_file()

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
                
            print(f"🔧 Updated job {job_id}: status={update.status}, active={update.active}, waiting={update.waiting}")
        else:
            print(f"❌ Job {job_id} not found in jobs dictionary")

    def update_job_status(self, job_id: str, status: str, active: bool = False, waiting: bool = False, result=None, error=None):
        """Update job status (simplified version for thread-based processing with shared storage)"""
        self._sync_jobs()  # Load latest from file first
        
        if job_id in self.jobs:
            # Update job data
            self.jobs[job_id].update({
                "status": status,
                "active": active,
                "waiting": waiting,
                "result": result,
                "error": error,
                "updated_at": datetime.utcnow().isoformat()
            })
            
            # Save to shared file
            self._save_jobs_to_file(self.jobs)
            
            print(f"🔧 Updated job {job_id}: status={status}, active={active}, waiting={waiting}")
        else:
            print(f"❌ Job {job_id} not found in jobs dictionary")

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID (from shared storage)"""
        self._sync_jobs()  # Load latest from file
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a job (from shared storage)"""
        self._sync_jobs()  # Load latest from file first
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs_to_file(self.jobs)  # Save after deletion
            return True
        return False

    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs (from shared storage)"""
        self._sync_jobs()  # Load latest from file
        return self.jobs

    def get_queue_status(self) -> Dict:
        """Get queue status and statistics with proper worker pool info"""
        try:
            # Count jobs by status
            total_jobs = len(self.jobs)
            completed_jobs = len([j for j in self.jobs.values() if j.get('status') == 'completed'])
            failed_jobs = len([j for j in self.jobs.values() if j.get('status') == 'failed'])
            processing_jobs = len([j for j in self.jobs.values() if j.get('status') == 'processing'])
            queued_jobs = len([j for j in self.jobs.values() if j.get('status') == 'queued'])
            
            # Get queue statistics with proper worker info
            with self.worker_lock:
                active_workers = self.active_workers
            
            queue_stats = {
                "queue_name": "pdf_processing",
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "processing_jobs": processing_jobs,
                "queued_jobs": queued_jobs,
                "max_workers": self.max_workers,
                "active_workers": active_workers,
                "available_workers": self.max_workers - active_workers,
            }
            
            # Get worker information from thread pool
            workers = []
            for i in range(self.max_workers):
                worker_name = f"pdf_worker_{i+1}"
                is_active = i < active_workers
                workers.append({
                    "name": worker_name,
                    "state": "active" if is_active else "idle",
                    "current_job": "",
                    "last_heartbeat": datetime.utcnow().isoformat()
                })
            
            # Get recent jobs
            recent_jobs = []
            sorted_jobs = sorted(self.jobs.items(), key=lambda x: x[1].get('created_at', ''), reverse=True)
            for job_id, job in sorted_jobs[:10]:  # Last 10 jobs
                recent_jobs.append({
                    "job_id": job_id,
                    "status": job.get('status', 'unknown'),
                    "created_at": job.get('created_at'),
                    "updated_at": job.get('updated_at'),
                    "result": str(job.get('result', ''))[:100] + "..." if job.get('result') and len(str(job.get('result'))) > 100 else job.get('result'),
                    "error": job.get('error'),
                    "filename": job.get('args', ['Unknown'])[1] if len(job.get('args', [])) > 1 else 'Unknown'
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
        """Get job by ID (simulated since RQ doesn't work with HTTP Redis)"""
        return self.get_job(job_id)

    def enqueue_job(self, func, *args, **kwargs):
        """Enqueue a job (simulated since RQ doesn't work with HTTP Redis)"""
        import uuid
        import threading
        import time
        
        # Generate a job ID
        job_id = str(uuid.uuid4())
        
        # Filter out RQ-specific kwargs that shouldn't be passed to the task function
        rq_kwargs = {
            'job_timeout', 'result_ttl', 'failure_ttl', 'job_id', 'depends_on',
            'timeout', 'retry', 'meta', 'description', 'at', 'in'
        }
        task_kwargs = {k: v for k, v in kwargs.items() if k not in rq_kwargs}
        
        # Create job entry
        job_data = {
            "id": job_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "args": list(args),  # Keep actual args, don't convert to strings
            "kwargs": task_kwargs,  # Only pass task-specific kwargs
            "result": None,
            "logs": [],
            "active": False,
            "waiting": True,
            "filename": args[1] if len(args) > 1 else "Unknown"  # Store filename for easier access
        }
        
        # Add to jobs dictionary and save to shared file
        self._sync_jobs()  # Load latest from file first
        self.jobs[job_id] = job_data
        self._save_jobs_to_file(self.jobs)
        
        # Submit job to worker pool (respects RQ_WORKERS limit)
        def process_job():
            with self.worker_lock:
                self.active_workers += 1
                worker_name = f"pdf_worker_{self.active_workers}"
            
            try:
                print(f"🔧 Worker {worker_name} starting job {job_id} ({args[1] if len(args) > 1 else 'unknown'})")
                
                # Update status to processing
                self.update_job_status(job_id, "processing", active=True, waiting=False)
                
                # Execute the function with filtered kwargs
                result = func(*args, **task_kwargs)
                
                # Update status to completed
                self.update_job_status(job_id, "completed", active=False, waiting=False, result=result)
                print(f"✅ Worker {worker_name} completed job {job_id}")
                
            except Exception as e:
                # Update status to failed
                self.update_job_status(job_id, "failed", active=False, waiting=False, error=str(e))
                print(f"❌ Worker {worker_name} failed job {job_id}: {e}")
            finally:
                with self.worker_lock:
                    self.active_workers -= 1
        
        # Submit to thread pool (this will queue if all workers are busy)
        future = self.executor.submit(process_job)
        print(f"📋 Job {job_id} queued (active workers: {self.active_workers}/{self.max_workers})")
        
        # Return a mock job object
        class MockJob:
            def __init__(self, job_id):
                self.id = job_id
        
        return MockJob(job_id)


# Global queue manager instance
queue_manager = QueueManager()
