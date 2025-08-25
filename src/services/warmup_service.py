import os
import asyncio
import threading
import tempfile
import shutil
import requests
import time
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from upstash_redis import Redis

from .pdf_processor import pdf_processor


class WarmupService:
    def __init__(self):
        self.warmup_dir = Path("warmup_files")
        self.warmup_status = "not_started"
        self.api_base_url = "http://localhost:8000"
        
        # Initialize Redis connection for worker coordination
        self.redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
        self.redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        if not self.redis_url or not self.redis_token:
            print("⚠️  WARNING: Redis credentials not found, falling back to local coordination")
            self.redis_conn = None
        else:
            try:
                self.redis_conn = Redis(url=self.redis_url, token=self.redis_token)
                print("✅ Redis connection established for warmup coordination")
            except Exception as e:
                print(f"⚠️  WARNING: Could not connect to Redis: {e}, falling back to local coordination")
                self.redis_conn = None
        
        # Redis keys for coordination
        self.WARMUP_STATUS_KEY = "docling:warmup:status"
        self.WARMUP_LOCK_KEY = "docling:warmup:lock"
        self.WARMUP_WORKER_KEY = "docling:warmup:worker_id"
        
        # Worker identification
        self.worker_id = f"worker_{os.getpid()}"
        
        # Check if warmup is already completed by another worker
        self._check_redis_warmup_status()
        
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
        if not self.redis_conn:
            print(f"⚠️  No Redis connection, status not saved: {status}")
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
        if not self.redis_conn:
            print("⚠️  No Redis connection, cannot acquire lock")
            return True  # Allow warmup to proceed if no Redis
        
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
        if not self.redis_conn:
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
        """Start warmup process in background thread with Redis coordination"""
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
            print(f"🧪 Testing /ocr endpoint (synchronous) with {pdf_file.name}...")
            
            # Create temporary file for testing
            with open(pdf_file, 'rb') as f:
                files = {'file': (pdf_file.name, f, 'application/pdf')}
                response = requests.post(f"{self.api_base_url}/ocr", files=files, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"✅ /ocr endpoint test passed for {pdf_file.name}")
                    return True
                else:
                    print(f"❌ /ocr endpoint test failed for {pdf_file.name}: {result}")
                    return False
            else:
                print(f"❌ /ocr endpoint test failed for {pdf_file.name}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ /ocr endpoint test error for {pdf_file.name}: {str(e)}")
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
        """Test asynchronous OCR endpoint with multiple PDFs"""
        try:
            print(f"🧪 Testing /ocr/async endpoint (asynchronous) with {len(pdf_files)} PDF files...")
            
            success_count = 0
            total_files = len(pdf_files)
            
            for pdf_file in pdf_files:
                try:
                    print(f"   📄 Testing {pdf_file.name}...")
                    
                    # Submit async job
                    with open(pdf_file, 'rb') as f:
                        files = {'file': (pdf_file.name, f, 'application/pdf')}
                        response = requests.post(f"{self.api_base_url}/ocr/async", files=files, timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        job_id = result.get('job_id')
                        
                        if job_id:
                            print(f"   ✅ /ocr/async job submitted for {pdf_file.name}, job_id: {job_id}")
                            success_count += 1
                        else:
                            print(f"   ❌ /ocr/async job failed for {pdf_file.name}: No job_id returned")
                    else:
                        print(f"   ❌ /ocr/async job failed for {pdf_file.name}: HTTP {response.status_code}")
                        
                except Exception as e:
                    print(f"   ❌ /ocr/async job error for {pdf_file.name}: {str(e)}")
            
            # Consider test successful if at least 50% of files worked
            success_rate = success_count / total_files if total_files > 0 else 0
            if success_rate >= 0.5:
                print(f"✅ /ocr/async endpoint test passed: {success_count}/{total_files} files processed successfully")
                return True
            else:
                print(f"❌ /ocr/async endpoint test failed: {success_count}/{total_files} files processed successfully")
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
                print(f"📋 Testing /ocr endpoint with single file: {test_file.name}")
                sync_success = self._test_sync_ocr(test_file)
                
                # Test /ocr/async endpoint (asynchronous) with multiple files (up to 2 files)
                async_test_files = warmup_files[:2]  # Use up to 2 files for async testing
                print(f"📋 Testing /ocr/async endpoint with {len(async_test_files)} files: {[f.name for f in async_test_files]}")
                async_success = self._test_async_ocr_multiple(async_test_files)
                
                # Mark as ready if /ocr endpoint works
                if sync_success:
                    self.warmup_status = "ready"
                    self._set_redis_status("ready")
                    print("🎉 Warmup process completed! Both /ocr and /ocr/async endpoints tested successfully.")
                else:
                    self.warmup_status = "failed"
                    self._set_redis_status("failed")
                    print("❌ Warmup process failed: /ocr endpoint test failed")
            else:
                # No warmup files, mark as ready
                self.warmup_status = "ready"
                self._set_redis_status("ready")
                print("🎉 Warmup process completed! (No warmup files to test)")
            
            # Release Redis lock
            self._release_redis_lock()
            
        except Exception as e:
            print(f"❌ Warmup process failed: {str(e)}")
            self.warmup_status = "failed"
            self._set_redis_status("failed")
            
            # Release Redis lock on failure
            self._release_redis_lock()
    
    def get_status(self) -> Dict:
        """Get current warmup status, checking Redis for latest updates"""
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
        
        return {
            "status": self.warmup_status,
            "worker_id": self.worker_id,
            "redis_status": redis_status,
            "redis_worker": redis_worker
        }
    
    def is_ready(self) -> bool:
        """Check if API is ready to accept requests"""
        # Check Redis for latest status before returning
        self._check_redis_warmup_status()
        return self.warmup_status == "ready"


# Global warmup service instance
warmup_service = WarmupService()
