import os
import psutil
import asyncio
import queue
import threading
import json
import time
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
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
        self.jobs_archive_dir = Path("/tmp/docling_jobs_archive")
        self.jobs_archive_dir.mkdir(exist_ok=True)
        
        # Job file rotation settings
        self.max_file_size_mb = int(os.getenv('JOB_FILE_MAX_SIZE_MB', 10))  # 10MB default
        self.max_jobs_per_file = int(os.getenv('MAX_JOBS_PER_FILE', 100))  # 100 jobs default
        self.job_retention_hours = int(os.getenv('JOB_RETENTION_HOURS', 24))  # 24 hours default
        
        self._ensure_jobs_file()
        self.jobs: Dict[str, Dict] = {}
        
        # Track active workers
        self.active_workers = 0
        self.worker_lock = threading.Lock()
        
        # File lock for shared storage
        self.file_lock = threading.Lock()
        
        # Full results storage (separate from job tracking)
        self.results_dir = Path("/tmp/docling_results")
        self.results_dir.mkdir(exist_ok=True)

    def _ensure_jobs_file(self):
        """Ensure the jobs file exists"""
        if not self.jobs_file.exists():
            with open(self.jobs_file, 'w') as f:
                json.dump({}, f)
    
    def _load_jobs_from_file(self) -> Dict[str, Dict]:
        """Load jobs from shared file storage with robust error handling"""
        try:
            if not self.jobs_file.exists():
                return {}
                
            with open(self.jobs_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return {}
                jobs_data = json.loads(content)
                return jobs_data if isinstance(jobs_data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Error loading jobs from file: {e}")
            return {}
    
    def _filter_job_data_for_storage(self, job_data: Dict) -> Dict:
        """Filter job data to remove large objects before storage"""
        filtered_job = job_data.copy()
        
        # Remove large data from args (PDF bytes)
        if 'args' in filtered_job and isinstance(filtered_job['args'], list):
            filtered_args = []
            for arg in filtered_job['args']:
                if isinstance(arg, bytes):
                    filtered_args.append(f"<bytes_data_size_{len(arg)}>")
                elif isinstance(arg, str) and len(arg) > 1000:
                    filtered_args.append(f"{arg[:100]}...<truncated_size_{len(arg)}>")
                else:
                    filtered_args.append(arg)
            filtered_job['args'] = filtered_args
        
        # Limit result size
        if 'result' in filtered_job and filtered_job['result']:
            result = filtered_job['result']
            if isinstance(result, dict):
                # Keep only essential result fields and limit size
                filtered_result = {}
                for key, value in result.items():
                    if key in ['status', 'filename', 'pages', 'total_characters', 'processing_time']:
                        filtered_result[key] = value
                    elif isinstance(value, str) and len(value) > 500:
                        filtered_result[key] = f"{value[:100]}...<truncated_size_{len(value)}>"
                    elif isinstance(value, list) and len(value) > 10:
                        filtered_result[key] = f"<list_with_{len(value)}_items>"
                    else:
                        filtered_result[key] = value
                filtered_job['result'] = filtered_result
            elif isinstance(result, str) and len(result) > 1000:
                filtered_job['result'] = f"{result[:200]}...<truncated_size_{len(result)}>"
        
        # Limit logs to last 10 entries
        if 'logs' in filtered_job and isinstance(filtered_job['logs'], list):
            filtered_job['logs'] = filtered_job['logs'][-10:]
        
        return filtered_job

    def _create_result_summary(self, result) -> Dict:
        """Create a lightweight summary of the result for job tracking"""
        if not result or not isinstance(result, dict):
            return result
        
        summary = {
            "status": result.get("status"),
            "filename": result.get("filename"),
            "processing_time": result.get("processing_time"),
            "pages": 0,
            "total_characters": 0,
            "files_generated": []
        }
        
        # Count pages and characters from files
        if "files" in result and isinstance(result["files"], dict):
            summary["files_generated"] = list(result["files"].keys())
            for file_type, content in result["files"].items():
                if isinstance(content, str):
                    summary["total_characters"] += len(content)
                    if file_type in ["markdown", "json"]:
                        # Count pages by estimating from content length
                        summary["pages"] = max(summary["pages"], len(content) // 2000 + 1)
        
        # Add truncated samples for preview
        if "files" in result and isinstance(result["files"], dict):
            preview_files = {}
            for file_type, content in result["files"].items():
                if isinstance(content, str) and len(content) > 0:
                    preview_files[file_type] = {
                        "size_chars": len(content),
                        "preview": content[:200] + "..." if len(content) > 200 else content
                    }
            summary["file_previews"] = preview_files
        
        return summary

    def _store_full_result(self, job_id: str, result):
        """Store the full result separately from job tracking"""
        try:
            result_file = self.results_dir / f"{job_id}.json"
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"💾 Stored full result for job {job_id}")
        except Exception as e:
            print(f"⚠️ Error storing full result for {job_id}: {e}")

    def _get_full_result(self, job_id: str):
        """Retrieve the full result for a job"""
        try:
            result_file = self.results_dir / f"{job_id}.json"
            if result_file.exists():
                with open(result_file, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"⚠️ Error loading full result for {job_id}: {e}")
            return None

    def _check_file_rotation_needed(self) -> bool:
        """Check if job file needs rotation based on size or job count"""
        if not self.jobs_file.exists():
            return False
            
        # Check file size
        file_size_mb = self.jobs_file.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_file_size_mb:
            print(f"📁 Job file size ({file_size_mb:.1f}MB) exceeds limit ({self.max_file_size_mb}MB)")
            return True
        
        # Check job count
        if len(self.jobs) > self.max_jobs_per_file:
            print(f"📁 Job count ({len(self.jobs)}) exceeds limit ({self.max_jobs_per_file})")
            return True
            
        return False

    def _rotate_jobs_file(self):
        """Rotate the current jobs file to archive and start fresh"""
        try:
            if not self.jobs_file.exists():
                return
                
            # Create archive filename with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            archive_filename = f"jobs_{timestamp}.json.gz"
            archive_path = self.jobs_archive_dir / archive_filename
            
            # Compress and move current file to archive
            with open(self.jobs_file, 'rb') as f_in:
                with gzip.open(archive_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            print(f"📁 Rotated jobs file to {archive_path}")
            
            # Remove old file and create new empty one
            self.jobs_file.unlink()
            self._ensure_jobs_file()
            
            # Clean up old archives
            self._cleanup_old_archives()
            
        except Exception as e:
            print(f"⚠️ Error rotating jobs file: {e}")

    def _cleanup_old_archives(self):
        """Remove archive files older than retention period"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.job_retention_hours)
            
            for archive_file in self.jobs_archive_dir.glob("jobs_*.json.gz"):
                if archive_file.stat().st_mtime < cutoff_time.timestamp():
                    archive_file.unlink()
                    print(f"🗑️ Deleted old archive: {archive_file.name}")
                    
        except Exception as e:
            print(f"⚠️ Error cleaning up archives: {e}")

    def _save_jobs_to_file(self, jobs_data: Dict[str, Dict]):
        """Save jobs to shared file storage using atomic write with rotation"""
        import tempfile
        import os
        
        try:
            # Check if rotation is needed before saving
            if self._check_file_rotation_needed():
                self._rotate_jobs_file()
                # Clear in-memory jobs after rotation (keep only recent ones)
                recent_jobs = {}
                cutoff_time = datetime.utcnow() - timedelta(hours=1)  # Keep last hour
                for job_id, job_data in jobs_data.items():
                    created_at = datetime.fromisoformat(job_data.get('created_at', ''))
                    if created_at > cutoff_time:
                        recent_jobs[job_id] = job_data
                jobs_data = recent_jobs
            
            # Filter job data to remove large objects
            filtered_jobs = {}
            for job_id, job_data in jobs_data.items():
                filtered_jobs[job_id] = self._filter_job_data_for_storage(job_data)
            
            # Write to temporary file first (atomic operation)
            temp_file = self.jobs_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(filtered_jobs, f, indent=2, default=str)
                f.flush()  # Ensure data is written
                os.fsync(f.fileno())  # Force write to disk
            
            # Atomic rename (this is atomic on most filesystems)
            os.rename(temp_file, self.jobs_file)
            
            # Update in-memory jobs with filtered data
            self.jobs = filtered_jobs
            
        except Exception as e:
            print(f"⚠️ Error saving jobs to file: {e}")
            # Clean up temp file if it exists
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except:
                pass
    
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
            # Filter the result before storing to prevent massive file sizes
            filtered_result = None
            if result is not None:
                filtered_result = self._create_result_summary(result)
            
            # Update job data
            self.jobs[job_id].update({
                "status": status,
                "active": active,
                "waiting": waiting,
                "result": filtered_result,
                "error": error,
                "updated_at": datetime.utcnow().isoformat()
            })
            
            # Store the full result separately for retrieval (not in job file)
            if result is not None and status == "completed":
                self._store_full_result(job_id, result)
            
            # Save to shared file
            self._save_jobs_to_file(self.jobs)
            
            print(f"🔧 Updated job {job_id}: status={status}, active={active}, waiting={waiting}")
        else:
            print(f"❌ Job {job_id} not found in jobs dictionary")

    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID (from shared storage) with full result if available"""
        self._sync_jobs()  # Load latest from file
        job_data = self.jobs.get(job_id)
        
        if job_data and job_data.get("status") == "completed":
            # Try to get the full result and merge it back
            full_result = self._get_full_result(job_id)
            if full_result:
                job_data = job_data.copy()
                job_data["result"] = full_result
        
        return job_data

    def delete_job(self, job_id: str) -> bool:
        """Delete a job (from shared storage)"""
        self._sync_jobs()  # Load latest from file first
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs_to_file(self.jobs)  # Save after deletion
            
            # Also delete the full result file if it exists
            try:
                result_file = self.results_dir / f"{job_id}.json"
                if result_file.exists():
                    result_file.unlink()
                    print(f"🗑️ Deleted full result file for job {job_id}")
            except Exception as e:
                print(f"⚠️ Error deleting result file for {job_id}: {e}")
            
            return True
        return False

    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs (from shared storage)"""
        self._sync_jobs()  # Load latest from file
        return self.jobs

    def get_storage_info(self) -> Dict:
        """Get information about job storage and file sizes"""
        try:
            storage_info = {
                "current_file": {
                    "path": str(self.jobs_file),
                    "exists": self.jobs_file.exists(),
                    "size_mb": 0,
                    "job_count": len(self.jobs)
                },
                "archive_dir": {
                    "path": str(self.jobs_archive_dir),
                    "exists": self.jobs_archive_dir.exists(),
                    "archive_count": 0,
                    "total_archive_size_mb": 0
                },
                "results_dir": {
                    "path": str(self.results_dir),
                    "exists": self.results_dir.exists(),
                    "result_files": 0,
                    "total_results_size_mb": 0
                },
                "settings": {
                    "max_file_size_mb": self.max_file_size_mb,
                    "max_jobs_per_file": self.max_jobs_per_file,
                    "retention_hours": self.job_retention_hours
                }
            }
            
            # Get current file size
            if self.jobs_file.exists():
                storage_info["current_file"]["size_mb"] = self.jobs_file.stat().st_size / (1024 * 1024)
            
            # Get archive information
            if self.jobs_archive_dir.exists():
                archive_files = list(self.jobs_archive_dir.glob("jobs_*.json.gz"))
                storage_info["archive_dir"]["archive_count"] = len(archive_files)
                total_size = sum(f.stat().st_size for f in archive_files)
                storage_info["archive_dir"]["total_archive_size_mb"] = total_size / (1024 * 1024)
            
            # Get results directory information
            if self.results_dir.exists():
                result_files = list(self.results_dir.glob("*.json"))
                storage_info["results_dir"]["result_files"] = len(result_files)
                total_size = sum(f.stat().st_size for f in result_files)
                storage_info["results_dir"]["total_results_size_mb"] = total_size / (1024 * 1024)
            
            return storage_info
            
        except Exception as e:
            return {"error": str(e)}

    def cleanup_jobs(self, hours_old: int = None) -> Dict:
        """Manually cleanup old jobs and force rotation if needed"""
        try:
            hours_old = hours_old or self.job_retention_hours
            
            # Cleanup old archives
            self._cleanup_old_archives()
            
            # Force rotation if file is too large
            if self._check_file_rotation_needed():
                self._rotate_jobs_file()
                
            # Remove old jobs from memory
            if hours_old > 0:
                cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)
                original_count = len(self.jobs)
                
                # Collect old job IDs before filtering
                old_job_ids = [
                    job_id for job_id, job_data in self.jobs.items()
                    if datetime.fromisoformat(job_data.get('created_at', '')) <= cutoff_time
                ]
                
                # Filter jobs
                self.jobs = {
                    job_id: job_data for job_id, job_data in self.jobs.items()
                    if datetime.fromisoformat(job_data.get('created_at', '')) > cutoff_time
                }
                
                # Clean up old result files
                cleaned_results = 0
                for job_id in old_job_ids:
                    try:
                        result_file = self.results_dir / f"{job_id}.json"
                        if result_file.exists():
                            result_file.unlink()
                            cleaned_results += 1
                    except Exception as e:
                        print(f"⚠️ Error cleaning result file {job_id}: {e}")
                
                removed_count = original_count - len(self.jobs)
                
                # Save cleaned jobs
                self._save_jobs_to_file(self.jobs)
                
                return {
                    "status": "success",
                    "removed_jobs": removed_count,
                    "cleaned_result_files": cleaned_results,
                    "remaining_jobs": len(self.jobs),
                    "cutoff_hours": hours_old
                }
            
            return {"status": "success", "message": "Cleanup completed"}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
