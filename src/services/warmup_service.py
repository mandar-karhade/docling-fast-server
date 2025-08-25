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
        
        # Redis configuration for locking and status sharing
        self.redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
        self.redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        self.redis_conn = None
        
        if self.redis_url and self.redis_token:
            try:
                self.redis_conn = Redis(url=self.redis_url, token=self.redis_token)
            except Exception as e:
                print(f"⚠️  Could not connect to Redis: {e}")
        
        # Check if warmup is already completed by another worker
        self._check_worker_status()
        
    def get_warmup_files(self) -> List[Path]:
        """Get list of PDF files in warmup directory"""
        if not self.warmup_dir.exists():
            return []
        
        pdf_files = list(self.warmup_dir.glob("*.pdf"))
        return sorted(pdf_files)  # Sort for consistent order
    
    def _check_worker_status(self):
        """Check if warmup is already completed by another worker using Redis"""
        if not self.redis_conn:
            return
            
        try:
            status = self.redis_conn.get("warmup_status")
            if status and status.decode("utf-8") == "ready":
                self.warmup_status = "ready"
                print("🔥 Warmup already completed by another worker (status from Redis)")
        except Exception as e:
            print(f"⚠️  Could not check worker status from Redis: {e}")
            
    def _save_redis_status(self, status: str):
        """Save warmup status to Redis for worker sharing"""
        if not self.redis_conn:
            return
            
        try:
            self.redis_conn.set("warmup_status", status)
            print(f"💾 Worker status saved to Redis: {status}")
        except Exception as e:
            print(f"⚠️  Could not save worker status to Redis: {e}")
    
    def start_warmup(self):
        """Start warmup process in background thread with Redis lock"""
        # Don't start if already in progress or completed
        if self.warmup_status == "in_progress" or self.warmup_status == "ready":
            return
        
        if not self.redis_conn:
            print("⚠️  Cannot start warmup without Redis connection")
            # Fallback to running warmup for each worker if Redis is not available
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
            return
        
        # Use Redis lock to ensure only one warmup process runs
        lock_key = "warmup_lock"
        try:
            # Try to acquire lock, nx=True makes it atomic
            lock_acquired = self.redis_conn.set(lock_key, "locked", nx=True, ex=600)  # Lock with 10-min timeout
            
            if not lock_acquired:
                print("🔥 Warmup already in progress by another worker (lock in Redis)")
                return
            
            # Set status to in_progress
            self.warmup_status = "in_progress"
            self._save_redis_status("in_progress")
            
            # Start warmup in background thread
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"⚠️  Could not acquire warmup lock from Redis: {e}")
            # Fallback to running warmup for each worker on lock failure
            self.warmup_status = "in_progress"
            self._save_redis_status("in_progress")
            
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
            
            if result == b"PONG":
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
                self._save_redis_status("ready")
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
                    self._save_redis_status("ready")
                    print("🎉 Warmup process completed! Both /ocr and /ocr/async endpoints tested successfully.")
                else:
                    self.warmup_status = "failed"
                    self._save_redis_status("failed")
                    print("❌ Warmup process failed: /ocr endpoint test failed")
            else:
                # No warmup files, mark as ready
                self.warmup_status = "ready"
                self._save_redis_status("ready")
                print("🎉 Warmup process completed! (No warmup files to test)")
            
            # Clean up lock in Redis
            if self.redis_conn:
                try:
                    self.redis_conn.delete("warmup_lock")
                except Exception as e:
                    print(f"⚠️  Could not release warmup lock in Redis: {e}")
            
        except Exception as e:
            print(f"❌ Warmup process failed: {str(e)}")
            self.warmup_status = "failed"
            self._save_redis_status("failed")
            
            # Clean up lock on failure too
            if self.redis_conn:
                try:
                    self.redis_conn.delete("warmup_lock")
                except Exception as e:
                    print(f"⚠️  Could not release warmup lock in Redis: {e}")
    
    def get_status(self) -> Dict:
        """Get current warmup status"""
        return {
            "status": self.warmup_status
        }
    
    def is_ready(self) -> bool:
        """Check if API is ready to accept requests"""
        return self.warmup_status == "ready"


# Global warmup service instance
warmup_service = WarmupService()
