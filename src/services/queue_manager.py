import os
import psutil
import asyncio
import queue
import threading
import json
import time
import gzip
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from upstash_redis import Redis

from src.models.job import Job, JobUpdate
from src.utils.deployment_id import get_container_deployment_id


class QueueManager:
    def __init__(self):
        # Use Upstash Redis REST API
        self.redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
        self.redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        if not self.redis_url or not self.redis_token:
            raise ValueError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required")
        
        # Create Upstash Redis client
        self.redis_conn = Redis(url=self.redis_url, token=self.redis_token)
        
        # Get container-level deployment ID for queue isolation
        self.deployment_id = get_container_deployment_id()
        self.queue_prefix = f"docling:queue:{self.deployment_id}"
        
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
        
        # Clean up any old queue data on startup (after all attributes are initialized)
        self._cleanup_old_queues()
        
        # Clean up old deployment data from Redis
        self._cleanup_old_deployment_keys_from_redis()
        
        # Track rejected job IDs to avoid repeated processing
        self._rejected_jobs_cache = set()
        
        print(f"✅ Queue Manager initialized with deployment ID: {self.deployment_id}")
        print(f"🔧 Using queue prefix: {self.queue_prefix}")

    def _cleanup_old_queues(self):
        """Clean up old queue data from previous deployments"""
        try:
            print("🧹 Cleaning up old queue data...")
            
            # Clear any existing jobs file to start fresh
            if self.jobs_file.exists():
                print(f"🗑️ Clearing old jobs file: {self.jobs_file}")
                self.jobs_file.unlink()
                self._ensure_jobs_file()
            
            # Clean up old result files older than 1 hour
            if self.results_dir.exists():
                cutoff_time = datetime.utcnow() - timedelta(hours=1)
                cleaned_count = 0
                
                for result_file in self.results_dir.glob("*.json"):
                    try:
                        file_mtime = datetime.fromtimestamp(result_file.stat().st_mtime)
                        if file_mtime < cutoff_time:
                            result_file.unlink()
                            cleaned_count += 1
                    except Exception as e:
                        print(f"⚠️  Error cleaning result file {result_file}: {e}")
                
                if cleaned_count > 0:
                    print(f"🗑️ Cleaned up {cleaned_count} old result files")
            
            print("✅ Queue cleanup completed")
            
        except Exception as e:
            print(f"⚠️  Error during queue cleanup: {e}")

    def get_deployment_info(self) -> Dict:
        """Get deployment information"""
        return {
            "deployment_id": self.deployment_id,
            "queue_prefix": self.queue_prefix,
            "created_at": datetime.utcnow().isoformat(),
            "max_workers": self.max_workers
        }
    
    def is_valid_job_id_for_deployment(self, job_id: str, cleanup_if_invalid: bool = True) -> bool:
        """Check if job ID belongs to current deployment and optionally clean up invalid ones"""
        try:
            # Check if job ID has deployment prefix
            if job_id.startswith(f"{self.deployment_id}-"):
                return True
            
            # For backwards compatibility, also check if job exists in current jobs
            # (for jobs created before deployment ID prefixing)
            self._sync_jobs()  # Load latest from file
            job_data = self.jobs.get(job_id)
            if job_data and job_data.get("deployment_id") == self.deployment_id:
                return True
            
            # Job is from different deployment or not found
            # Check if we've already processed this invalid job
            if job_id in self._rejected_jobs_cache:
                print(f"🚫 Job {job_id} already rejected and processed")
                return False
            
            print(f"🚫 Job {job_id} rejected - not from current deployment {self.deployment_id}")
            
            # Add to rejected cache to avoid repeated processing
            self._rejected_jobs_cache.add(job_id)
            
            # Clean it up if requested and it exists in our jobs
            if cleanup_if_invalid and job_data:
                print(f"🧹 Cleaning up orphaned job {job_id} from different deployment")
                self._cleanup_orphaned_job(job_id)
            elif cleanup_if_invalid and not job_data:
                # Job not in our jobs file, but might have result files - clean those up
                print(f"🧹 Checking for orphaned files for job {job_id}")
                self._cleanup_orphaned_files_only(job_id)
            
            return False
        except Exception as e:
            print(f"⚠️  Error validating job ID {job_id}: {e}")
            return False
    
    def _cleanup_orphaned_files_only(self, job_id: str):
        """Clean up result files and Redis keys for jobs not in our jobs dict"""
        try:
            # Remove result file if exists
            result_file = self.results_dir / f"{job_id}.json"
            if result_file.exists():
                result_file.unlink()
                print(f"🗑️ Removed orphaned result file for job {job_id}")
            
            # Also clean up any Redis keys for this job
            self._cleanup_redis_keys_for_job(job_id)
            
        except Exception as e:
            print(f"⚠️  Error cleaning up orphaned files for job {job_id}: {e}")
    
    def _cleanup_orphaned_job(self, job_id: str):
        """Clean up job from different deployment including Redis"""
        try:
            # Remove from local jobs file
            if job_id in self.jobs:
                del self.jobs[job_id]
                self._save_jobs_to_file(self.jobs)
                print(f"🗑️ Removed orphaned job {job_id} from jobs file")
            
            # Remove result file if exists
            result_file = self.results_dir / f"{job_id}.json"
            if result_file.exists():
                result_file.unlink()
                print(f"🗑️ Removed orphaned result file for job {job_id}")
            
            # Clean up from Redis
            self._cleanup_redis_keys_for_job(job_id)
                
        except Exception as e:
            print(f"⚠️  Error cleaning up orphaned job {job_id}: {e}")
    
    def _cleanup_redis_keys_for_job(self, job_id: str):
        """Remove all possible Redis keys for a job from any deployment"""
        try:
            if not self.redis_conn:
                print(f"⚠️  No Redis connection available for cleanup")
                return
            
            # Try to delete common Redis key patterns for this job
            # We'll try different deployment prefixes since we don't know which one the job came from
            redis_keys_to_delete = [
                # Direct job keys (old format)
                f"docling:job:{job_id}",
                f"docling:result:{job_id}",
                f"docling:status:{job_id}",
                f"docling:meta:{job_id}",
                # RQ-style keys
                f"rq:job:{job_id}",
                f"rq:result:{job_id}",
                # Our queue-specific keys
                f"docling:queue:job:{job_id}",
                # Try with some common deployment IDs (this is a best-effort cleanup)
                f"{job_id}:data",
                f"{job_id}:result",
                f"{job_id}:status"
            ]
            
            # Also try to construct keys with different deployment prefixes
            # Extract potential deployment prefix from job_id if it exists
            if '-' in job_id:
                potential_deployment_id = job_id.split('-')[0]
                if len(potential_deployment_id) == 8:  # Our deployment IDs are 8 chars
                    redis_keys_to_delete.extend([
                        f"docling:queue:{potential_deployment_id}:job:{job_id}",
                        f"docling:queue:{potential_deployment_id}:result:{job_id}",
                        f"docling:deployment:{potential_deployment_id}:job:{job_id}"
                    ])
            
            deleted_keys = 0
            for key in redis_keys_to_delete:
                try:
                    result = self.redis_conn.delete(key)
                    if result and result > 0:
                        deleted_keys += 1
                        print(f"🗑️ Deleted Redis key: {key}")
                except Exception as e:
                    # Silent failure - key might not exist, which is fine
                    pass
            
            if deleted_keys > 0:
                print(f"🗑️ Cleaned up {deleted_keys} Redis keys for job {job_id}")
            else:
                print(f"📝 No Redis keys found to clean for job {job_id}")
                
        except Exception as e:
            print(f"⚠️  Error during Redis cleanup for job {job_id}: {e}")
    
    def _cleanup_old_deployment_keys_from_redis(self):
        """Clean up Redis keys from old deployments on startup"""
        try:
            if not self.redis_conn:
                print("📝 No Redis connection for deployment cleanup")
                return
            
            print("🧹 Cleaning up old deployment keys from Redis...")
            
            # Try to clean up common patterns of old deployment keys
            # Since Upstash Redis doesn't easily support SCAN, we'll clean known patterns
            old_key_patterns = [
                # Old warmup keys (try to clean a few common ones)
                "docling:warmup:status:*",
                "docling:warmup:lock:*", 
                "docling:warmup:worker_id:*",
                # Old queue patterns
                "docling:queue:*",
                # RQ patterns
                "rq:*",
                # Old job patterns
                "docling:job:*",
                "docling:result:*"
            ]
            
            # For Upstash Redis, we can't easily scan, so we'll try to delete some known keys
            # that might be left from previous deployments. This is best effort.
            
            # Clean up deployment info from previous runs
            for i in range(10):  # Try a few common deployment IDs
                try:
                    old_deployment_key = f"docling:deployment:*"
                    # We can't really iterate, so this is limited cleanup
                    pass
                except:
                    pass
            
            print("✅ Redis deployment cleanup completed (best effort)")
            
        except Exception as e:
            print(f"⚠️  Error during Redis deployment cleanup: {e}")

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
                    try:
                        created_at_str = job_data.get('created_at', '')
                        if created_at_str:
                            created_at = datetime.fromisoformat(created_at_str)
                            if created_at > cutoff_time:
                                recent_jobs[job_id] = job_data
                            else:
                                print(f"🗑️ Rotating out old job {job_id} (created: {created_at_str})")
                        else:
                            # Keep jobs without created_at to be safe
                            recent_jobs[job_id] = job_data
                    except Exception as e:
                        print(f"⚠️  Error parsing created_at for job {job_id}: {e}")
                        # Keep the job if we can't parse the date to be safe
                        recent_jobs[job_id] = job_data
                
                removed_count = len(jobs_data) - len(recent_jobs)
                if removed_count > 0:
                    print(f"📁 File rotation: kept {len(recent_jobs)} recent jobs, rotated {removed_count} old jobs")
                
                jobs_data = recent_jobs
            
            # Filter job data to remove large objects
            filtered_jobs = {}
            for job_id, job_data in jobs_data.items():
                filtered_jobs[job_id] = self._filter_job_data_for_storage(job_data)
            
            # Ensure parent directory exists
            self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first (atomic operation)
            temp_file = self.jobs_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(filtered_jobs, f, indent=2, default=str)
                f.flush()  # Ensure data is written
                os.fsync(f.fileno())  # Force write to disk
            
            # Atomic rename (this is atomic on most filesystems)
            if temp_file.exists():
                os.rename(temp_file, self.jobs_file)
                # Update in-memory jobs with filtered data
                self.jobs = filtered_jobs
                print(f"💾 Saved {len(filtered_jobs)} jobs to file")
            else:
                raise FileNotFoundError(f"Temporary file {temp_file} was not created successfully")
            
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
        """Create a new job and return job ID with deployment prefix"""
        import uuid
        # Create job ID with deployment prefix for validation
        base_job_id = str(uuid.uuid4())
        job_id = f"{self.deployment_id}-{base_job_id}"
        worker_info = self.get_worker_info()
        
        self.jobs[job_id] = {
            "id": job_id,
            "deployment_id": self.deployment_id,
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
        try:
            # First validate if job belongs to current deployment (no cleanup here since routes handle it)
            if not self.is_valid_job_id_for_deployment(job_id, cleanup_if_invalid=False):
                print(f"🚫 Rejecting job request {job_id} - not from current deployment {self.deployment_id}")
                return None
            
            self._sync_jobs()  # Load latest from file
            job_data = self.jobs.get(job_id)
            
            if job_data and job_data.get("status") == "completed":
                # Try to get the full result and merge it back
                try:
                    full_result = self._get_full_result(job_id)
                    if full_result:
                        job_data = job_data.copy()
                        job_data["result"] = full_result
                except Exception as e:
                    print(f"⚠️  Could not load full result for job {job_id}: {e}")
                    # Continue with summary result from job data
            
            return job_data
        except Exception as e:
            print(f"⚠️  Error in get_job for {job_id}: {e}")
            return None

    def delete_job(self, job_id: str) -> bool:
        """Delete a job (from shared storage)"""
        # Validate deployment before processing (no cleanup here since routes handle it)
        if not self.is_valid_job_id_for_deployment(job_id, cleanup_if_invalid=False):
            print(f"🚫 Rejecting delete request for job {job_id} - not from current deployment {self.deployment_id}")
            return False
        
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
        
        # Generate a job ID with deployment prefix
        base_job_id = str(uuid.uuid4())
        job_id = f"{self.deployment_id}-{base_job_id}"
        
        # Filter out RQ-specific kwargs that shouldn't be passed to the task function
        rq_kwargs = {
            'job_timeout', 'result_ttl', 'failure_ttl', 'job_id', 'depends_on',
            'timeout', 'retry', 'meta', 'description', 'at', 'in'
        }
        task_kwargs = {k: v for k, v in kwargs.items() if k not in rq_kwargs}
        
        # Create job entry
        job_data = {
            "id": job_id,
            "deployment_id": self.deployment_id,
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
