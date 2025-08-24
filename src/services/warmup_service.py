import os
import asyncio
import threading
import tempfile
import shutil
import requests
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
        
    def get_warmup_files(self) -> List[Path]:
        """Get list of PDF files in warmup directory"""
        if not self.warmup_dir.exists():
            return []
        
        pdf_files = list(self.warmup_dir.glob("*.pdf"))
        return sorted(pdf_files)  # Sort for consistent order
    
    def start_warmup(self):
        """Start warmup process in background thread"""
        if self.warmup_status == "in_progress":
            return
        
        self.warmup_status = "in_progress"
        self.start_time = datetime.now()
        self.warmup_results = []
        self.warmup_errors = []
        
        # Start warmup in background thread
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
            import redis
            from src.services.queue_manager import queue_manager
            
            # Test Redis connection
            redis_conn = queue_manager.redis_conn
            result = redis_conn.ping()
            
            if result:
                print("✅ Redis connection test passed")
                return True
            else:
                print("❌ Redis connection test failed: ping returned False")
                return False
                
        except Exception as e:
            print(f"❌ Redis connection test failed: {str(e)}")
            return False
    
    def _test_async_ocr(self, pdf_file: Path) -> bool:
        """Test asynchronous OCR endpoint"""
        try:
            print(f"🧪 Testing asynchronous OCR with {pdf_file.name}...")
            
            # Submit async job
            with open(pdf_file, 'rb') as f:
                files = {'file': (pdf_file.name, f, 'application/pdf')}
                response = requests.post(f"{self.api_base_url}/ocr/async", files=files, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                job_id = result.get('job_id')
                if job_id:
                    print(f"✅ Async job submitted for {pdf_file.name}, job_id: {job_id}")
                    
                    # Wait for job completion (max 2 minutes)
                    max_wait = 120
                    wait_time = 0
                    while wait_time < max_wait:
                        try:
                            job_response = requests.get(f"{self.api_base_url}/jobs/{job_id}", timeout=10)
                            if job_response.status_code == 200:
                                job_result = job_response.json()
                                status = job_result.get('status')
                                
                                if status == 'finished':
                                    print(f"✅ Asynchronous OCR test passed for {pdf_file.name}")
                                    return True
                                elif status == 'failed':
                                    error = job_result.get('error', 'Unknown error')
                                    print(f"❌ Asynchronous OCR test failed for {pdf_file.name}: {error}")
                                    return False
                                elif status in ['queued', 'started']:
                                    # Still processing, wait
                                    import time
                                    time.sleep(5)
                                    wait_time += 5
                                    continue
                                else:
                                    print(f"❌ Asynchronous OCR test failed for {pdf_file.name}: Unexpected status {status}")
                                    return False
                            else:
                                print(f"❌ Failed to check job status for {pdf_file.name}: HTTP {job_response.status_code}")
                                return False
                        except Exception as e:
                            print(f"❌ Error checking job status for {pdf_file.name}: {str(e)}")
                            return False
                    
                    print(f"❌ Asynchronous OCR test timeout for {pdf_file.name}")
                    return False
                else:
                    print(f"❌ Asynchronous OCR test failed for {pdf_file.name}: No job_id returned")
                    return False
            else:
                print(f"❌ Asynchronous OCR test failed for {pdf_file.name}: HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"❌ Error details: {error_detail}")
                except:
                    print(f"❌ Error response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Asynchronous OCR test error for {pdf_file.name}: {str(e)}")
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
            
            # Process each warmup file to load models
            for i, pdf_file in enumerate(warmup_files, 1):
                try:
                    print(f"🔄 Processing warmup file {i}/{len(warmup_files)}: {pdf_file.name}")
                    
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
                    
                except Exception as e:
                    error_msg = f"Error processing {pdf_file.name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    self.warmup_errors.append({
                        "file": pdf_file.name,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
            
            # Test API endpoints with the first warmup file
            if warmup_files:
                test_file = warmup_files[0]
                print(f"🧪 Testing API endpoints with {test_file.name}...")
                
                # Test synchronous OCR
                sync_success = self._test_sync_ocr(test_file)
                
                # Test Redis connection
                redis_success = self._test_redis_connection()
                
                # Test asynchronous OCR
                async_success = self._test_async_ocr(test_file)
                
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
            
        except Exception as e:
            print(f"❌ Warmup process failed: {str(e)}")
            self.warmup_status = "failed"
            self.warmup_errors.append({
                "file": "warmup_process",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            self.end_time = datetime.now()
    
    def get_status(self) -> Dict:
        """Get current warmup status"""
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
            }
        }
        
        if self.start_time:
            status["start_time"] = self.start_time.isoformat()
        
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
