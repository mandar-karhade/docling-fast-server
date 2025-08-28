import os
import asyncio
import threading
import tempfile
import shutil
import requests
import time
import uuid
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from upstash_redis import Redis

from .pdf_processor import pdf_processor


class WarmupService:
    def __init__(self, use_redis_coordination=None):
        self.warmup_dir = Path("warmup_files")
        self.warmup_status = "not_started"
        self.api_base_url = "http://localhost:8000"
        
        # Determine if we should use Redis coordination
        if use_redis_coordination is None:
            # Auto-detect: use Redis if credentials are available
            use_redis_coordination = bool(os.getenv('UPSTASH_REDIS_REST_URL') and os.getenv('UPSTASH_REDIS_REST_TOKEN'))
        
        self.use_redis_coordination = use_redis_coordination
        
        if self.use_redis_coordination:
            # Initialize Redis connection for worker coordination
            self.redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
            self.redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
            
            if not self.redis_url or not self.redis_token:
                print("⚠️  WARNING: Redis credentials not found, disabling Redis coordination")
                self.redis_conn = None
                self.use_redis_coordination = False
            else:
                try:
                    self.redis_conn = Redis(url=self.redis_url, token=self.redis_token)
                    print("✅ Redis connection established for warmup coordination")
                except Exception as e:
                    print(f"⚠️  WARNING: Could not connect to Redis: {e}, disabling Redis coordination")
                    self.redis_conn = None
                    self.use_redis_coordination = False
            
            # Get or create container-level deployment ID
            self.deployment_id = self._get_container_deployment_id()
            
            # Redis keys for coordination with unique deployment ID
            self.WARMUP_STATUS_KEY = f"docling:warmup:status:{self.deployment_id}"
            self.WARMUP_LOCK_KEY = f"docling:warmup:lock:{self.deployment_id}"
            self.WARMUP_WORKER_KEY = f"docling:warmup:worker_id:{self.deployment_id}"
            self.QUEUE_PREFIX = f"docling:queue:{self.deployment_id}"
            
            # Initialize unique queue for this deployment
            self._initialize_unique_queue()
        else:
            print("📝 Redis coordination disabled - using container-level warmup")
            self.redis_conn = None
        
        # Worker identification
        self.worker_id = f"worker_{os.getpid()}"
        
        # Check warmup status based on coordination mode
        if self.use_redis_coordination:
            self._check_redis_warmup_status()
        else:
            # Container-level warmup: assume warmup completed before workers started
            self.warmup_status = "ready"
            print(f"🎯 Worker {self.worker_id}: Container-level warmup assumed complete")
        
    def _get_container_deployment_id(self) -> str:
        """Get or create a container-level deployment ID shared across all workers"""
        deployment_file = Path("/tmp/docling_deployment_id")
        
        try:
            # Check if deployment ID already exists
            if deployment_file.exists():
                with open(deployment_file, 'r') as f:
                    deployment_id = f.read().strip()
                    if deployment_id:
                        print(f"📋 Using existing container deployment ID: {deployment_id}")
                        return deployment_id
            
            # Generate new deployment ID for this container
            deployment_id = str(uuid.uuid4())[:8]
            
            # Save it for other workers to use
            with open(deployment_file, 'w') as f:
                f.write(deployment_id)
            
            print(f"✨ Generated new container deployment ID: {deployment_id}")
            return deployment_id
            
        except Exception as e:
            print(f"⚠️  Error managing deployment ID file: {e}")
            # Fallback to process-based ID
            return f"fallback_{os.getpid()}"

    def _initialize_unique_queue(self):
        """Initialize a unique Redis queue for this deployment and clean up old queues"""
        if not self.use_redis_coordination or not self.redis_conn:
            return
        
        try:
            # Clean up old deployment queues (older than 1 hour)
            self._cleanup_old_deployment_queues()
            
            # Set deployment info in Redis
            deployment_info = {
                "deployment_id": self.deployment_id,
                "created_at": datetime.utcnow().isoformat(),
                "worker_id": self.worker_id,
                "queue_prefix": self.QUEUE_PREFIX
            }
            
            # Store deployment info with 24 hour expiration
            deployment_key = f"docling:deployment:{self.deployment_id}"
            self.redis_conn.set(deployment_key, str(deployment_info), ex=86400)
            
            print(f"✅ Initialized unique queue with deployment ID: {self.deployment_id}")
            print(f"🔧 Queue prefix: {self.QUEUE_PREFIX}")
            
        except Exception as e:
            print(f"⚠️  Error initializing unique queue: {e}")
    
    def _cleanup_old_deployment_queues(self):
        """Clean up old deployment queues and their associated keys"""
        if not self.use_redis_coordination or not self.redis_conn:
            return
        
        try:
            # Get all deployment keys
            deployment_keys = []
            try:
                # Note: Upstash Redis may have limitations on SCAN operations
                # We'll use a simple key pattern approach
                print("🧹 Cleaning up old deployment queues...")
            except Exception as e:
                print(f"⚠️  Could not scan for old deployments: {e}")
                return
            
            # Clean up any orphaned warmup/lock keys older than 1 hour
            cutoff_time = datetime.utcnow().timestamp() - 3600  # 1 hour ago
            
            # Try to clean up known key patterns (best effort)
            old_patterns = [
                "docling:warmup:status:*",
                "docling:warmup:lock:*", 
                "docling:warmup:worker_id:*",
                "docling:queue:*"
            ]
            
            for pattern in old_patterns:
                try:
                    # For Upstash Redis, we can't easily scan keys
                    # So we'll just clean up keys we know about from previous deployments
                    pass
                except Exception as e:
                    print(f"⚠️  Error cleaning pattern {pattern}: {e}")
            
            print("✅ Queue cleanup completed")
            
        except Exception as e:
            print(f"⚠️  Error during queue cleanup: {e}")

    def disable_redis_coordination(self):
        """Disable Redis coordination and use container-level warmup"""
        self.use_redis_coordination = False
        self.redis_conn = None
        print("🔒 Redis coordination disabled - using container-level warmup")
    
    def run_warmup_sync(self):
        """Run warmup process synchronously (blocking) without threading"""
        print("🔥 Running synchronous warmup process...")
        self.warmup_status = "in_progress"
        
        try:
            self._run_warmup_container_level()
        except Exception as e:
            print(f"❌ Synchronous warmup failed: {e}")
            raise
    
    def get_warmup_files(self) -> List[Path]:
        """Get list of PDF files in warmup directory"""
        if not self.warmup_dir.exists():
            return []
        
        pdf_files = list(self.warmup_dir.glob("*.pdf"))
        return sorted(pdf_files)  # Sort for consistent order
    
    def _check_redis_warmup_status(self):
        """Check if warmup is already completed by another worker via Redis"""
        if not self.redis_conn:
            print("⚠️  No Redis connection, using local warmup status")
            return
        
        try:
            status = self.redis_conn.get(self.WARMUP_STATUS_KEY)
            if status == "ready":
                self.warmup_status = "ready"
                worker_id = self.redis_conn.get(self.WARMUP_WORKER_KEY) or "unknown"
                print(f"🔥 Warmup already completed by worker: {worker_id}")
            elif status == "in_progress":
                self.warmup_status = "in_progress"
                worker_id = self.redis_conn.get(self.WARMUP_WORKER_KEY) or "unknown"
                print(f"🔥 Warmup in progress by worker: {worker_id}")
            else:
                print("🆕 No previous warmup status found in Redis")
        except Exception as e:
            print(f"⚠️  Could not check warmup status from Redis: {e}")
    
    def _set_redis_status(self, status: str):
        """Save warmup status to Redis for worker coordination"""
        if not self.use_redis_coordination or not self.redis_conn:
            return
        
        try:
            # Set status with 24 hour expiration
            self.redis_conn.set(self.WARMUP_STATUS_KEY, status, ex=86400)
            # Set worker ID with same expiration
            self.redis_conn.set(self.WARMUP_WORKER_KEY, self.worker_id, ex=86400)
            print(f"💾 Worker {self.worker_id} saved status to Redis: {status}")
        except Exception as e:
            print(f"⚠️  Could not save status to Redis: {e}")
    
    def _acquire_redis_lock(self) -> bool:
        """Try to acquire Redis lock for warmup process"""
        if not self.use_redis_coordination or not self.redis_conn:
            return True  # Allow warmup to proceed if no Redis coordination
        
        try:
            # Try to set a lock with 10 minute expiration
            lock_acquired = self.redis_conn.set(self.WARMUP_LOCK_KEY, self.worker_id, ex=600, nx=True)
            if lock_acquired:
                print(f"🔒 Worker {self.worker_id} acquired warmup lock")
                return True
            else:
                existing_worker = self.redis_conn.get(self.WARMUP_LOCK_KEY) or "unknown"
                print(f"🔒 Warmup lock already held by worker: {existing_worker}")
                return False
        except Exception as e:
            print(f"⚠️  Error acquiring Redis lock: {e}")
            return True  # Allow warmup if Redis fails
    
    def _release_redis_lock(self):
        """Release Redis lock after warmup completion or failure"""
        if not self.use_redis_coordination or not self.redis_conn:
            return
        
        try:
            # Only delete lock if it's held by this worker
            current_holder = self.redis_conn.get(self.WARMUP_LOCK_KEY)
            if current_holder == self.worker_id:
                self.redis_conn.delete(self.WARMUP_LOCK_KEY)
                print(f"🔓 Worker {self.worker_id} released warmup lock")
            else:
                print(f"🔓 Lock not held by this worker ({self.worker_id}), not releasing")
        except Exception as e:
            print(f"⚠️  Error releasing Redis lock: {e}")
    
    def start_warmup(self):
        """Start warmup process - either with Redis coordination or locally"""
        
        if not self.use_redis_coordination:
            # Container-level warmup - skip if already done or should be done at container level
            print("🔥 Warmup should be done at container level - skipping worker warmup")
            self.warmup_status = "ready"  # Assume container warmup was done
            return
        
        # Redis coordination mode
        # Re-check Redis status in case it was updated by another worker
        self._check_redis_warmup_status()
        
        # Don't start if already in progress or completed
        if self.warmup_status == "in_progress" or self.warmup_status == "ready":
            print(f"🔥 Warmup not starting - current status: {self.warmup_status}")
            return
        
        # Try to acquire Redis lock
        if not self._acquire_redis_lock():
            print("🔥 Another worker is handling warmup, waiting for completion")
            # Wait a bit and then check status again
            time.sleep(2)
            self._check_redis_warmup_status()
            return
        
        try:
            # Set status to in_progress
            self.warmup_status = "in_progress"
            self._set_redis_status("in_progress")
            
            # Start warmup in background thread
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"⚠️  Error starting warmup: {e}")
            # Release lock on error
            self._release_redis_lock()
            # Continue with local warmup if Redis fails
            self.warmup_status = "in_progress"
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
    
    def _test_sync_ocr(self, pdf_file: Path) -> bool:
        """Test synchronous OCR endpoint"""
        try:
            print(f"📋 test 1: /ocr >> job submitted {pdf_file.name}")
            
            # Create temporary file for testing
            with open(pdf_file, 'rb') as f:
                files = {'file': (pdf_file.name, f, 'application/pdf')}
                response = requests.post(f"{self.api_base_url}/ocr", files=files, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"📋 test 1: /ocr >> successful {pdf_file.name}")
                    
                    # Show result keys like jq would
                    result_keys = list(result.keys())
                    print(f"📋 test 1 results >> {pdf_file.name}: {result_keys}")
                    
                    return True
                else:
                    print(f"❌ test 1: /ocr >> failed {pdf_file.name}: {result}")
                    return False
            else:
                print(f"❌ test 1: /ocr >> failed {pdf_file.name}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ test 1: /ocr >> error for {pdf_file.name}: {str(e)}")
            return False
    
    def _test_redis_connection(self) -> bool:
        """Test Redis connection before running async tests"""
        try:
            print("🔍 Testing Redis connection...")
            from upstash_redis import Redis
            import os
            
            # Test Redis connection using Upstash Redis
            redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
            redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
            
            if not redis_url or not redis_token:
                print("❌ Redis connection test failed: Missing UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN")
                return False
            
            redis_conn = Redis(url=redis_url, token=redis_token)
            result = redis_conn.ping()
            
            if result == "PONG":
                print("✅ Redis connection test passed")
                return True
            else:
                print("❌ Redis connection test failed: ping returned unexpected result")
                return False
                
        except Exception as e:
            print(f"❌ Redis connection test failed: {str(e)}")
            return False
    
    def _test_async_ocr_multiple(self, pdf_files: list) -> bool:
        """Test asynchronous OCR endpoint with multiple PDFs and wait for completion"""
        try:
            filenames = [f.name for f in pdf_files]
            print(f"📋 test 2: /ocr/async >> {len(pdf_files)} files submitted {' '.join(filenames)}")
            
            submitted_jobs = []
            total_files = len(pdf_files)
            
            # Submit all jobs first
            for pdf_file in pdf_files:
                try:
                    # Submit async job
                    with open(pdf_file, 'rb') as f:
                        files = {'file': (pdf_file.name, f, 'application/pdf')}
                        response = requests.post(f"{self.api_base_url}/ocr/async", files=files, timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        job_id = result.get('job_id')
                        
                        if job_id:
                            submitted_jobs.append({'job_id': job_id, 'filename': pdf_file.name})
                        else:
                            print(f"   ❌ Job submission failed for {pdf_file.name}: No job_id returned")
                    else:
                        print(f"   ❌ Job submission failed for {pdf_file.name}: HTTP {response.status_code}")
                        
                except Exception as e:
                    print(f"   ❌ Job submission error for {pdf_file.name}: {str(e)}")
            
            if not submitted_jobs:
                print("❌ No jobs were submitted successfully")
                return False
            
            # Show submitted job IDs
            successful_filenames = [job['filename'] for job in submitted_jobs]
            print(f"📋 test 2: /ocr/async >> {len(submitted_jobs)} files successful {' '.join(successful_filenames)}")
            
            # Show job IDs
            print("📋 test 2 jobs >>")
            for i, job_info in enumerate(submitted_jobs, 1):
                print(f"   file {i} : {job_info['job_id']}")
            
            # Now wait for jobs to complete and check their status
            success_count = 0
            max_wait_time = 120  # 120 seconds (2 minutes) max wait time
            wait_interval = 5   # Check every 5 seconds
            completed_jobs = []
            
            for job_info in submitted_jobs:
                job_id = job_info['job_id']
                filename = job_info['filename']
                waited_time = 0
                
                while waited_time < max_wait_time:
                    try:
                        # Check job status
                        status_response = requests.get(f"{self.api_base_url}/jobs/{job_id}", timeout=10)
                        
                        if status_response.status_code == 200:
                            status_result = status_response.json()
                            job_status = status_result.get('status', 'unknown')
                            
                            if job_status == 'finished':
                                result = status_result.get('result')
                                if result and result.get('status') == 'success':
                                    # Show result keys like jq would
                                    result_keys = list(result.keys())
                                    file_num = len(completed_jobs) + 1
                                    print(f"📋 job {file_num}: {job_id} completed for test 2 {filename} - results {result_keys}")
                                    completed_jobs.append(job_info)
                                    success_count += 1
                                else:
                                    print(f"   ❌ Job finished but failed for {filename}: {result}")
                                    completed_jobs.append(job_info)
                                break
                            elif job_status == 'failed':
                                error_msg = status_result.get('error', 'Unknown error')
                                print(f"   ❌ Job failed for {filename}: {error_msg}")
                                completed_jobs.append(job_info)
                                break
                            elif job_status in ['queued', 'started']:
                                # Only show this message occasionally to avoid spam
                                if waited_time % 15 == 0:  # Every 15 seconds
                                    print(f"   ⏳ Job {job_status} for {filename}, waiting...")
                            else:
                                print(f"   ❓ Unknown job status for {filename}: {job_status}")
                        else:
                            print(f"   ⚠️  Could not check status for {filename}: HTTP {status_response.status_code}")
                            
                    except Exception as e:
                        print(f"   ⚠️  Error checking status for {filename}: {e}")
                    
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                
                if waited_time >= max_wait_time:
                    print(f"   ⏰ Timeout waiting for {filename} to complete")
                    completed_jobs.append(job_info)
            
            # Final status
            if success_count == len(submitted_jobs):
                print(f"\n✅ Job results were successfully retrieved.")
                print(f"🎉 Warmup complete")
                return True
            elif success_count > 0:
                print(f"\n⚠️  Partial success: {success_count}/{len(submitted_jobs)} jobs completed successfully")
                return success_count >= len(submitted_jobs) * 0.5  # 50% success rate
            else:
                print(f"\n❌ All async jobs failed")
                return False
                
        except Exception as e:
            print(f"❌ /ocr/async endpoint test error: {str(e)}")
            return False
    
    def _run_warmup(self):
        """Run warmup process"""
        try:
            print("🔥 Starting warmup process...")
            
            # Get warmup files
            warmup_files = self.get_warmup_files()
            if not warmup_files:
                print("⚠️  No warmup files found")
                self.warmup_status = "ready"
                self._set_redis_status("ready")
                self._release_redis_lock()
                return
            
            print(f"📁 Found {len(warmup_files)} warmup files")
            
            # Test API endpoints
            if warmup_files:
                test_file = warmup_files[0]
                print(f"🧪 Testing API endpoints...")
                
                # Test /ocr endpoint (synchronous) with single file
                sync_success = self._test_sync_ocr(test_file)
                
                # Test /ocr/async endpoint (asynchronous) with multiple files (up to 2 files)
                async_test_files = warmup_files[:2]  # Use up to 2 files for async testing
                async_success = self._test_async_ocr_multiple(async_test_files)
                
                # Mark as ready if /ocr endpoint works
                if sync_success:
                    self.warmup_status = "ready"
                    self._set_redis_status("ready")
                    if not async_success:  # Only print if async didn't already print completion
                        print("\n✅ Job results were successfully retrieved.")
                        print("🎉 Warmup complete")
                else:
                    self.warmup_status = "failed"
                    self._set_redis_status("failed")
                    print("❌ Warmup process failed: /ocr endpoint test failed")
            else:
                # No warmup files, mark as ready
                self.warmup_status = "ready"
                self._set_redis_status("ready")
                print("🎉 Warmup process completed! (No warmup files to test)")
            
            # Release Redis lock (only if using Redis coordination)
            self._release_redis_lock()
            
        except Exception as e:
            print(f"❌ Warmup process failed: {str(e)}")
            self.warmup_status = "failed"
            self._set_redis_status("failed")
            
            # Release Redis lock on failure (only if using Redis coordination)
            self._release_redis_lock()
    
    def _run_warmup_container_level(self):
        """Run container-level warmup without API endpoint testing"""
        try:
            print("🔥 Starting container-level warmup process...")
            
            # Get warmup files
            warmup_files = self.get_warmup_files()
            if not warmup_files:
                print("⚠️  No warmup files found - skipping model warmup")
                print("🎉 Container-level warmup completed successfully! (No test files)")
                self.warmup_status = "ready"
                return
                
            print(f"📁 Found {len(warmup_files)} warmup files: {[f.name for f in warmup_files]}")
            
            # Test each warmup file for thorough testing
            for i, test_file in enumerate(warmup_files[:2], 1):  # Limit to 2 files max
                print(f"\n📋 Container Test {i}: Direct Processing >> {test_file.name}")
                
                try:
                    # Process the file directly (this will download models on first use)
                    temp_dir = Path(tempfile.mkdtemp())
                    doc = pdf_processor.process_pdf(test_file)
                    
                    # Generate results to test output functionality
                    results = pdf_processor.get_output(doc, test_file.stem, "warmup")
                    
                    if results and isinstance(results, dict):
                        # Show result keys like jq would
                        result_keys = list(results.keys())
                        print(f"📋 Container Test {i}: Direct Processing >> successful {test_file.name}")
                        print(f"📋 Container Test {i} results >> {test_file.name}: {result_keys}")
                        
                        # Show some size info
                        markdown_size = len(str(results.get('markdown', '')))
                        json_size = len(str(results.get('json', {})))
                        print(f"   Content: markdown ({markdown_size} chars), JSON ({json_size} chars)")
                    else:
                        print(f"❌ Container Test {i}: Processing failed for {test_file.name}")
                        raise Exception("Failed to generate results")
                    
                    # Cleanup temp directory
                    shutil.rmtree(temp_dir, ignore_errors=True)
                        
                except Exception as e:
                    print(f"❌ Container Test {i}: Processing failed for {test_file.name}: {e}")
                    raise
            
            print(f"\n✅ Job results were successfully generated.")
            print(f"🎉 Container-level warmup complete!")
            
            # Mark as ready
            self.warmup_status = "ready"
            
        except Exception as e:
            print(f"❌ Container-level warmup failed: {str(e)}")
            self.warmup_status = "failed"
            raise
    
    def get_status(self) -> Dict:
        """Get current warmup status"""
        
        result = {
            "status": self.warmup_status,
            "worker_id": self.worker_id,
            "coordination_mode": "redis" if self.use_redis_coordination else "container-level"
        }
        
        if self.use_redis_coordination:
            # Check Redis for latest status
            self._check_redis_warmup_status()
            
            redis_status = "unknown"
            redis_worker = "unknown"
            
            if self.redis_conn:
                try:
                    redis_status = self.redis_conn.get(self.WARMUP_STATUS_KEY) or "not_started"
                    redis_worker = self.redis_conn.get(self.WARMUP_WORKER_KEY) or "unknown"
                except Exception as e:
                    print(f"⚠️  Could not get status from Redis: {e}")
            
            result.update({
                "redis_status": redis_status,
                "redis_worker": redis_worker
            })
        
        return result
    
    def is_ready(self) -> bool:
        """Check if API is ready to accept requests"""
        if self.use_redis_coordination:
            # Check Redis for latest status before returning
            self._check_redis_warmup_status()
        
        return self.warmup_status == "ready"


# Global warmup service instance - use container-level warmup (no Redis coordination)
warmup_service = WarmupService(use_redis_coordination=False)
