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
        self.is_warmup_complete = False
        self.warmup_status = "not_started"
        self.warmup_results = []
        self.warmup_errors = []
        self.start_time = None
        self.end_time = None
        self.api_base_url = "http://localhost:8000"
        
        # Progress tracking
        self.total_steps = 0
        self.completed_steps = 0
        self.current_step = ""
        self.is_timed_out = False
        
    def get_warmup_files(self) -> List[Path]:
        """Get list of PDF files in warmup directory"""
        if not self.warmup_dir.exists():
            return []
        
        pdf_files = list(self.warmup_dir.glob("*.pdf"))
        return sorted(pdf_files)  # Sort for consistent order
    
    def check_timeout(self) -> bool:
        """Check if warmup has exceeded 5 minutes"""
        if not self.start_time:
            return False
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 300:  # 5 minutes
            self.is_timed_out = True
            return True
        return False
    
    def force_complete(self):
        """Force complete warmup due to timeout"""
        self.warmup_status = "timed_out"
        self.is_warmup_complete = True
        self.end_time = datetime.now()
        self.warmup_errors.append({
            "file": "warmup_timeout",
            "error": "Warmup process timed out after 5 minutes",
            "timestamp": datetime.now().isoformat()
        })
        
        # Clean up lock file
        try:
            lock_file = Path("/tmp/warmup.lock")
            if lock_file.exists():
                lock_file.unlink()
        except:
            pass
        
        print("⏰ Warmup process timed out after 5 minutes")
    
    def start_warmup(self):
        """Start warmup process in background thread"""
        if self.warmup_status == "in_progress":
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
            
            self.warmup_status = "in_progress"
            self.start_time = datetime.now()
            self.warmup_results = []
            self.warmup_errors = []
            self.is_timed_out = False
            self.completed_steps = 0
            self.total_steps = 0
            self.current_step = ""
            
            # Start warmup in background thread
            thread = threading.Thread(target=self._run_warmup, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"⚠️  Could not create warmup lock: {e}")
            # Continue without lock if we can't create it
            self.warmup_status = "in_progress"
            self.start_time = datetime.now()
            self.warmup_results = []
            self.warmup_errors = []
            self.is_timed_out = False
            self.completed_steps = 0
            self.total_steps = 0
            self.current_step = ""
            
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
                self.warmup_status = "no_files"
                self.is_warmup_complete = True
                self.end_time = datetime.now()
                return
            
            print(f"📁 Found {len(warmup_files)} warmup files")
            
            # Calculate total steps: warmup files + sync test + redis test + async test
            self.total_steps = len(warmup_files) + 3  # +3 for sync, redis, and async tests
            
            # Process each warmup file to load models
            for i, pdf_file in enumerate(warmup_files, 1):
                # Check for timeout
                if self.check_timeout():
                    self.force_complete()
                    return
                
                self.current_step = f"Processing warmup file {i}/{len(warmup_files)}: {pdf_file.name}"
                try:
                    print(f"🔄 {self.current_step}")
                    
                    # Create temporary directory for processing
                    temp_dir = tempfile.mkdtemp()
                    temp_path = Path(temp_dir)
                    
                    try:
                        # Process the file using pdf_processor to load models
                        doc = pdf_processor.process_pdf(pdf_file, temp_path)
                        
                        # Store result
                        self.warmup_results.append({
                            "file": pdf_file.name,
                            "status": "success",
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        print(f"✅ Warmup file {pdf_file.name} processed successfully")
                        
                    finally:
                        # Clean up temporary directory
                        try:
                            shutil.rmtree(temp_dir)
                        except:
                            pass
                    
                    self.completed_steps += 1
                    
                except Exception as e:
                    error_msg = f"Error processing {pdf_file.name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    self.warmup_errors.append({
                        "file": pdf_file.name,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    self.completed_steps += 1
            
            # Check for timeout before endpoint tests
            if self.check_timeout():
                self.force_complete()
                return
            
            # Test API endpoints
            if warmup_files:
                test_file = warmup_files[0]
                print(f"🧪 Testing API endpoints with {test_file.name}...")
                
                # Test synchronous OCR with single file
                self.current_step = "Testing synchronous OCR endpoint"
                sync_success = self._test_sync_ocr(test_file)
                self.completed_steps += 1
                
                # Check for timeout
                if self.check_timeout():
                    self.force_complete()
                    return
                
                # Test Redis connection
                self.current_step = "Testing Redis connection"
                redis_success = self._test_redis_connection()
                self.completed_steps += 1
                
                # Check for timeout
                if self.check_timeout():
                    self.force_complete()
                    return
                
                # Test asynchronous OCR with multiple files (up to 2 files)
                async_test_files = warmup_files[:2]  # Use up to 2 files for async testing
                self.current_step = f"Testing asynchronous OCR with {len(async_test_files)} files"
                async_success = self._test_async_ocr_multiple(async_test_files)
                self.completed_steps += 1
                
                # Store endpoint test results
                self.warmup_results.append({
                    "file": "sync_ocr_test",
                    "status": "success" if sync_success else "failed",
                    "timestamp": datetime.now().isoformat()
                })
                
                self.warmup_results.append({
                    "file": "async_ocr_test",
                    "status": "success" if async_success else "failed",
                    "timestamp": datetime.now().isoformat()
                })
                
                self.warmup_results.append({
                    "file": "redis_test",
                    "status": "success" if redis_success else "failed",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Mark as ready if sync OCR works, async is optional (depends on Redis)
                if sync_success:
                    if async_success:
                        self.warmup_status = "completed"
                        self.is_warmup_complete = True
                        print("🎉 Warmup process completed! Both OCR endpoints tested successfully. API is ready to accept requests.")
                    else:
                        self.warmup_status = "completed"
                        self.is_warmup_complete = True
                        print("🎉 Warmup process completed! Synchronous OCR working. Async OCR requires Redis connection. API is ready to accept requests.")
                else:
                    self.warmup_status = "failed"
                    print("❌ Warmup process failed: Synchronous OCR endpoint test failed")
                    if not sync_success:
                        print("❌ Synchronous OCR endpoint test failed")
                    if not async_success:
                        print("⚠️  Asynchronous OCR endpoint test failed (Redis connection issue)")
            else:
                # No warmup files, mark as completed
                self.warmup_status = "completed"
                self.is_warmup_complete = True
                print("🎉 Warmup process completed! (No warmup files to test)")
            
            self.end_time = datetime.now()
            self.current_step = "Completed"
            
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
            self.warmup_errors.append({
                "file": "warmup_process",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            self.end_time = datetime.now()
            
            # Clean up lock file on failure too
            try:
                lock_file = Path("/tmp/warmup.lock")
                if lock_file.exists():
                    lock_file.unlink()
            except:
                pass
    
    def get_status(self) -> Dict:
        """Get current warmup status"""
        # Check for timeout
        if self.check_timeout():
            self.force_complete()
        
        status = {
            "warmup_complete": self.is_warmup_complete,
            "status": self.warmup_status,
            "results": self.warmup_results,
            "errors": self.warmup_errors,
            "files_processed": len([r for r in self.warmup_results if r.get('file') not in ['sync_ocr_test', 'async_ocr_test', 'redis_test']]),
            "files_failed": len(self.warmup_errors),
            "endpoint_tests": {
                "sync_ocr": next((r for r in self.warmup_results if r.get('file') == 'sync_ocr_test'), {}).get('status', 'not_tested'),
                "async_ocr": next((r for r in self.warmup_results if r.get('file') == 'async_ocr_test'), {}).get('status', 'not_tested'),
                "redis_connection": next((r for r in self.warmup_results if r.get('file') == 'redis_test'), {}).get('status', 'not_tested')
            },
            # Progress tracking
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "progress_percentage": (self.completed_steps / self.total_steps * 100) if self.total_steps > 0 else 0,
            "current_step": self.current_step,
            "is_timed_out": self.is_timed_out
        }
        
        if self.start_time:
            status["start_time"] = self.start_time.isoformat()
            
            # Calculate estimated remaining time
            if self.total_steps > 0 and self.completed_steps > 0:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                avg_time_per_step = elapsed / self.completed_steps
                remaining_steps = self.total_steps - self.completed_steps
                estimated_remaining = avg_time_per_step * remaining_steps
                status["estimated_remaining_seconds"] = max(0, estimated_remaining)
            else:
                status["estimated_remaining_seconds"] = 0
        
        if self.end_time:
            status["end_time"] = self.end_time.isoformat()
            if self.start_time:
                duration = (self.end_time - self.start_time).total_seconds()
                status["duration_seconds"] = duration
        
        return status
    
    def is_ready(self) -> bool:
        """Check if API is ready to accept requests"""
        return self.is_warmup_complete and self.warmup_status == "completed"


# Global warmup service instance
warmup_service = WarmupService()
