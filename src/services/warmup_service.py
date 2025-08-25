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

from .pdf_processor import pdf_processor


class WarmupService:
    def __init__(self):
        self.warmup_dir = Path("warmup_files")
        self.warmup_status = "not_started"
        self.api_base_url = "http://localhost:8000"
        
        # Check if warmup is already completed by another worker
        self._check_global_completion()
        
    def get_warmup_files(self) -> List[Path]:
        """Get list of PDF files in warmup directory"""
        if not self.warmup_dir.exists():
            return []
        
        pdf_files = list(self.warmup_dir.glob("*.pdf"))
        return sorted(pdf_files)  # Sort for consistent order
    

    
    def _check_global_completion(self):
        """Check if warmup is already completed by another worker using Redis"""
        try:
            from upstash_redis import Redis
            import os
            
            # Get Redis connection
            redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
            redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
            
            if not redis_url or not redis_token:
                print("⚠️  Could not check global completion: Missing Redis credentials")
                return
            
            redis_conn = Redis(url=redis_url, token=redis_token)
            
            # Check if warmup is completed
            status = redis_conn.get("warmup:status")
            
            if status and status == "ready":
                self.warmup_status = "ready"
                print("🔥 Warmup already completed by another worker (Redis)")
        except Exception as e:
            print(f"⚠️  Could not check global completion: {e}")
    
    def _save_redis_status(self, status: str):
        """Save warmup status to Redis"""
        try:
            from upstash_redis import Redis
            import os
            
            # Get Redis connection
            redis_url = os.getenv('UPSTASH_REDIS_REST_URL')
            redis_token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
            
            if not redis_url or not redis_token:
                print("⚠️  Could not save Redis status: Missing Redis credentials")
                return
            
            redis_conn = Redis(url=redis_url, token=redis_token)
            
            # Save status to Redis with 24-hour expiration
            redis_conn.setex("warmup:status", 86400, status)
            print(f"💾 Warmup status saved to Redis: {status}")
                
        except Exception as e:
            print(f"⚠️  Could not save Redis status: {e}")
    

    
    def start_warmup(self):
        """Start warmup process in background thread"""
        # Don't start if already in progress or completed
        if self.warmup_status == "in_progress" or self.warmup_status == "ready":
            return
        
        # Use a file lock to ensure only one warmup process runs
        lock_file = Path("/tmp/warmup.lock")
        try:
            if lock_file.exists():
                # Check if lock is stale (older than 10 minutes)
                lock_age = time.time() - lock_file.stat().st_mtime
                if lock_age > 600:  # 10 minutes
                    lock_file.unlink()
                else:
                    print("🔥 Warmup already in progress by another worker")
                    return
            
            # Create lock file
            lock_file.touch()
            
            # Set status to in_progress
            self.warmup_status = "in_progress"
            self._save_redis_status("in_progress")
            
            # Start warmup in background thread
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"⚠️  Could not create warmup lock: {e}")
            # Continue without lock if we can't create it
            self.warmup_status = "in_progress"
            self._save_redis_status("in_progress")
            
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
    
    def _test_sync_ocr(self, pdf_file: Path) -> bool:
        """Test synchronous OCR endpoint"""
        try:
            print(f"🧪 Testing synchronous OCR with {pdf_file.name}...")
            
            # Create temporary file for testing
            with open(pdf_file, 'rb') as f:
                files = {'file': (pdf_file.name, f, 'application/pdf')}
                response = requests.post(f"{self.api_base_url}/ocr", files=files, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    print(f"✅ Synchronous OCR test passed for {pdf_file.name}")
                    return True
                else:
                    print(f"❌ Synchronous OCR test failed for {pdf_file.name}: {result}")
                    return False
            else:
                print(f"❌ Synchronous OCR test failed for {pdf_file.name}: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Synchronous OCR test error for {pdf_file.name}: {str(e)}")
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
            print(f"🧪 Testing asynchronous OCR with {len(pdf_files)} PDF files...")
            
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
                            print(f"   ✅ Async job submitted for {pdf_file.name}, job_id: {job_id}")
                            success_count += 1
                        else:
                            print(f"   ❌ Async job failed for {pdf_file.name}: No job_id returned")
                    else:
                        print(f"   ❌ Async job failed for {pdf_file.name}: HTTP {response.status_code}")
                        
                except Exception as e:
                    print(f"   ❌ Async job error for {pdf_file.name}: {str(e)}")
            
            # Consider test successful if at least 50% of files worked
            success_rate = success_count / total_files if total_files > 0 else 0
            if success_rate >= 0.5:
                print(f"✅ Asynchronous OCR test passed: {success_count}/{total_files} files processed successfully")
                return True
            else:
                print(f"❌ Asynchronous OCR test failed: {success_count}/{total_files} files processed successfully")
                return False
                
        except Exception as e:
            print(f"❌ Asynchronous OCR test error: {str(e)}")
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
                print(f"🧪 Testing API endpoints with {test_file.name}...")
                
                # Test synchronous OCR with single file
                sync_success = self._test_sync_ocr(test_file)
                
                # Test asynchronous OCR with multiple files (up to 2 files)
                async_test_files = warmup_files[:2]  # Use up to 2 files for async testing
                async_success = self._test_async_ocr_multiple(async_test_files)
                
                # Mark as ready if sync OCR works
                if sync_success:
                    self.warmup_status = "ready"
                    self._save_redis_status("ready")
                    print("🎉 Warmup process completed! API is ready to accept requests.")
                else:
                    self.warmup_status = "failed"
                    self._save_redis_status("failed")
                    print("❌ Warmup process failed: Synchronous OCR endpoint test failed")
            else:
                # No warmup files, mark as ready
                self.warmup_status = "ready"
                self._save_redis_status("ready")
                print("🎉 Warmup process completed! (No warmup files to test)")
            
            # Clean up lock file
            try:
                lock_file = Path("/tmp/warmup.lock")
                if lock_file.exists():
                    lock_file.unlink()
            except:
                pass
            
        except Exception as e:
            print(f"❌ Warmup process failed: {str(e)}")
            self.warmup_status = "failed"
            self._save_redis_status("failed")
            
            # Clean up lock file on failure too
            try:
                lock_file = Path("/tmp/warmup.lock")
                if lock_file.exists():
                    lock_file.unlink()
            except:
                pass
    
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
