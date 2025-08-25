"""
RunPod Integration Service with Clean Docling-Serve API
Handles dynamic pod creation/management for cloud-based document processing

COMPLETE PIPELINE:
PostgreSQL (db_state) → RunPod CUDA processing → MinIO storage by filetype
"""

import os
import logging
import asyncio
import httpx
import json
import base64
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import _minio_endpoint, _minio_access_key, _minio_secret_key, _minio_bucket
from app.core.timezone_utils import now_cst, format_cst_timestamp, format_cst_iso, duration_since_cst
from app.core.db_state_service import DbStateService
from app.models.db_state import ProcessingStatus, DbStateUpdate

logger = logging.getLogger(__name__)


class CleanDoclingAPI:
    """Clean docling-serve REST API client (no Gradio dependencies)"""
    
    def __init__(self, base_url: str = "http://localhost:5001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=300.0)
        
        # Configuration matching our tested implementation
        self.config = {
            "to_formats": ["json", "md", "html", "text", "doctags"],  # All 5 formats
            "image_export_mode": "embedded",
            "pipeline": "standard", 
            "ocr": True,
            "force_ocr": False,
            "ocr_engine": "easyocr",
            "ocr_lang": ["en", "fr", "de", "es"],
            "pdf_backend": "dlparse_v4",
            "table_mode": "accurate",
            "abort_on_error": False,
            "do_code_enrichment": False,
            "do_formula_enrichment": False,
            "do_picture_classification": False,
            "do_picture_description": False,
        }
    
    async def process_file_with_base64(self, filename: str, file_data: bytes) -> Optional[Dict]:
        """Process file using clean REST API with base64 encoding"""
        
        try:
            # Encode file to base64 (proven method)
            base64_string = base64.b64encode(file_data).decode("utf-8")
            
            # Create sources exactly like our working implementation
            sources = [{
                "kind": "file", 
                "base64_string": base64_string, 
                "filename": filename
            }]
            
            # Create target for direct JSON response (not ZIP)
            target = {"kind": "inbody"}
            
            # Create full parameters 
            parameters = {
                "sources": sources,
                "options": self.config,
                "target": target
            }
            
            logger.info(f"🚀 Processing {filename} with docling-serve")
            
            # Submit task to /v1/convert/source/async 
            response = await self.client.post(
                f"{self.base_url}/v1/convert/source/async",
                json=parameters,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Task submission failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
                
            task_data = response.json()
            task_id = task_data.get("task_id")
            
            if not task_id:
                logger.error("❌ No task_id received")
                return None
                
            logger.info(f"✅ Task submitted: {task_id}")
            
            # Poll for completion
            result = await self._wait_for_completion(task_id)
            
            if result:
                logger.info(f"🎉 Successfully processed {filename}")
                return result
            else:
                logger.error(f"❌ Processing failed for {filename}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error processing {filename}: {e}")
            return None
    
    async def _wait_for_completion(self, task_id: str, timeout: int = 300) -> Optional[Dict]:
        """Wait for task completion and get results"""
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Poll status
                response = await self.client.get(
                    f"{self.base_url}/v1/status/poll/{task_id}?wait=15"
                )
                
                if response.status_code != 200:
                    logger.error(f"❌ Status poll failed: {response.status_code}")
                    return None
                    
                status_data = response.json()
                status = status_data.get("task_status")
                
                if status == "success":
                    # Get results
                    result_response = await self.client.get(
                        f"{self.base_url}/v1/result/{task_id}"
                    )
                    
                    if result_response.status_code == 200:
                        return result_response.json()
                    else:
                        logger.error(f"❌ Failed to get results: {result_response.status_code}")
                        return None
                        
                elif status in ("failure", "revoked"):
                    logger.error(f"❌ Task failed with status: {status}")
                    return None
                else:
                    logger.debug(f"⏳ Task status: {status}")
                    await asyncio.sleep(5)
                    
            except Exception as e:
                logger.error(f"❌ Error polling task: {e}")
                return None
                
        logger.error("⏰ Task timed out")
        return None


class MinIOFiletypeManager:
    """MinIO client with organized storage by filetype as folders"""
    
    def __init__(self):
        self.endpoint = _minio_endpoint
        self.access_key = _minio_access_key
        self.secret_key = _minio_secret_key
        self.base_bucket = _minio_bucket
        
        # Import here to avoid circular imports
        try:
            from minio import Minio
            from minio.error import S3Error
            self.Minio = Minio
            self.S3Error = S3Error
        except ImportError:
            logger.error("MinIO client not available")
            return
        
        self.client = self.Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=False  # Set to True for HTTPS
        )
        
        # Organized storage folders by filetype within main bucket
        self.folder_mapping = {
            'json': 'json/',
            'md': 'markdown/', 
            'html': 'html/',
            'text': 'text/',
            'doctags': 'doctags/'
        }
        
    async def ensure_base_bucket(self):
        """Ensure the main bucket exists (folders are created automatically)"""
        
        try:
            if not self.client.bucket_exists(self.base_bucket):
                self.client.make_bucket(self.base_bucket)
                logger.info(f"📦 Created main bucket: {self.base_bucket}")
            else:
                logger.debug(f"✅ Main bucket exists: {self.base_bucket}")
        except Exception as e:
            logger.error(f"❌ Error with main bucket {self.base_bucket}: {e}")
                
    async def save_document_by_filetype(self, content_hash: str, canonical_title: str, document_data: Dict) -> Dict[str, str]:
        """Save all document formats to appropriate folders within main bucket"""
        
        saved_urls = {}
        
        # Generate filename base from canonical title and content hash (same as PDF pattern)
        from app.models.content_hash_documents import sanitize_filename
        sanitized_title = sanitize_filename(canonical_title)
        
        filename_base = f"{sanitized_title}_{content_hash[:16]}"
        
        # Format mapping from docling response to our storage
        format_mapping = {
            'md_content': ('md', '.md'),
            'json_content': ('json', '.json'),
            'html_content': ('html', '.html'), 
            'text_content': ('text', '.txt'),
            'doctags_content': ('doctags', '.doctags')
        }
        
        for format_key, (folder_type, extension) in format_mapping.items():
            content = document_data.get(format_key)
            if content:
                try:
                    # Create full object path with folder prefix
                    folder_prefix = self.folder_mapping[folder_type]
                    object_key = f"{folder_prefix}{filename_base}{extension}"
                    
                    # Convert content to bytes
                    if isinstance(content, dict):
                        content_bytes = json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8')
                    elif isinstance(content, str):
                        content_bytes = content.encode('utf-8')
                    else:
                        content_bytes = str(content).encode('utf-8')
                    
                    # Upload to MinIO main bucket with folder structure
                    from io import BytesIO
                    self.client.put_object(
                        self.base_bucket,
                        object_key,
                        BytesIO(content_bytes),
                        len(content_bytes),
                        content_type='application/octet-stream'
                    )
                    
                    file_url = f"minio://{self.base_bucket}/{object_key}"
                    saved_urls[format_key] = file_url
                    logger.info(f"💾 Saved {format_key}: {file_url}")
                    
                except Exception as e:
                    logger.error(f"❌ Error saving {format_key}: {e}")
                    
        return saved_urls


class RunPodDoclingService:
    """Enhanced RunPod service with clean docling API and filetype storage"""
    
    def __init__(self):
        self.db_service = DbStateService()
        self.runpod_api_key = os.getenv('RUNPOD_API_KEY')
        self.runpod_template_id = os.getenv('RUNPOD_TEMPLATE_ID', 'fv9ha2jppg')
        self.runpod_base_url = 'https://rest.runpod.io/v1'
        
        # Environment variable for existing pod usage
        self.runpod_docling_url = os.getenv('RUNPOD_DOCLING_URL')
        
        if not self.runpod_api_key:
            logger.warning("RUNPOD_API_KEY not configured - cloud processing disabled")
        
        self.http_client = httpx.AsyncClient(
            timeout=600.0,  # 10 minutes for pod operations
            headers={
                'Authorization': f'Bearer {self.runpod_api_key}',
                'Content-Type': 'application/json'
            } if self.runpod_api_key else {}
        )
        
        # Initialize components
        self.docling_api = CleanDoclingAPI()
        self.minio_manager = MinIOFiletypeManager()
        
        # Track active pods
        self.active_pods = []
    
    async def existing_health_docling_service(self):
        """Check if existing RunPod docling service is healthy"""
        if self.runpod_docling_url:
            try:
                # Check health of the existing docling service
                health_url = f"{self.runpod_docling_url}/health"
                logger.info(f"🔍 Checking health: {health_url}")
                response = await self.http_client.get(health_url, timeout=10.0)
                
                if response.status_code == 200:
                    logger.info(f"✅ Docling service is healthy at {self.runpod_docling_url}")
                    return True, self.runpod_docling_url
                else:
                    logger.warning(f"⚠️ Docling service unhealthy - status: {response.status_code}")
                    return False, None
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to check existing docling service health: {e}")
                return False, None
        else:
            logger.info("📋 No existing RunPod URL configured - will create new pod")
            return False, None

    async def create_processing_pod(self, gpu_type: str = "NVIDIA RTX 4000 Ada Generation", include_env: bool = False) -> Dict[str, Any]:
        """Create a RunPod pod with enhanced GPU/CUDA configuration. Set include_env=True only when pod needs database/storage access"""
        
        if not self.runpod_api_key:
            return {"error": "RunPod API key not configured", "success": False}
        
        # Enhanced pod configuration with explicit GPU settings
        pod_config = {
            "cloudType": "SECURE",
            "gpuCount": 1,
            "gpuTypeIds": [gpu_type],
            "templateId": self.runpod_template_id,
            "name": f"libhub-docling-{format_cst_timestamp('%Y%m%d-%H%M%S')}",
            "ports": ["8080/http"],
            # Explicit GPU configuration for CUDA acceleration
            "dockerArgs": [
                "--gpus=all",  # Ensure all GPUs are available to container
                "--runtime=nvidia"  # Explicitly use NVIDIA runtime
            ]
        }
        
        # Add environment variables only when needed for actual processing
        if include_env:
            pod_config["env"] = {
                # Database configuration
                "POSTGRES_HOST": os.getenv('POSTGRES_HOST', 'host.docker.internal'),
                "POSTGRES_PORT": os.getenv('POSTGRES_PORT', '5432'),
                "POSTGRES_DB": os.getenv('POSTGRES_DB', 'libhub'),
                "POSTGRES_USER": os.getenv('POSTGRES_USER', 'postgres'),
                "POSTGRES_PASSWORD": os.getenv('POSTGRES_PASSWORD', 'postgres'),
                
                # MinIO configuration
                "MINIO_URL": f"http://{_minio_endpoint}",
                "MINIO_ACCESS_KEY": _minio_access_key,
                "MINIO_SECRET_KEY": _minio_secret_key,
                "MINIO_BUCKET": _minio_bucket,
                
                # Enhanced CUDA/GPU configuration
                "CUDA_VISIBLE_DEVICES": "0",  # Use first GPU
                "CUDA_MEMORY_FRACTION": "0.8",  # Use 80% of GPU memory
                "CUDA_LAUNCH_BLOCKING": "1",  # Synchronous CUDA operations for debugging
                
                # Docling processing configuration
                "DOCLING_THREADS": "16",
                "ENABLE_PICTURE_DESCRIPTION": "false",
                "BATCH_SIZE": "10",
                
                # Additional GPU optimization
                "NVIDIA_VISIBLE_DEVICES": "all",
                "NVIDIA_DRIVER_CAPABILITIES": "compute,utility"
            }
            pod_config["ports"].append("5001/http")  # Add docling-serve port
        
        try:
            logger.info(f"🚀 Creating RunPod with template {self.runpod_template_id}")
            logger.info(f"🎮 GPU Type: {gpu_type}")
            logger.info(f"🔧 Docker Args: {pod_config.get('dockerArgs', [])}")
            
            response = await self.http_client.post(
                f"{self.runpod_base_url}/pods",
                json=pod_config
            )
            response.raise_for_status()
            
            pod_data = response.json()
            pod_id = pod_data.get('id')
            
            if pod_id:
                self.active_pods.append(pod_id)
                logger.info(f"✅ Pod created: {pod_id}")
                logger.info(f"💰 Cost per hour: ${pod_data.get('costPerHr', 'Unknown')}")
                return {"success": True, "pod_id": pod_id, "pod_data": pod_data}
            else:
                logger.error(f"❌ Pod creation failed: {pod_data}")
                return {"success": False, "error": "No pod ID returned", "response": pod_data}
                
        except Exception as e:
            logger.error(f"❌ Failed to create pod: {e}")
            return {"success": False, "error": str(e)}

    async def verify_cuda_availability(self, pod_id: str) -> bool:
        """Verify that CUDA is properly available on the pod"""
        
        logger.info(f"🔍 Verifying CUDA availability on pod {pod_id}")
        
        try:
            # Test CUDA availability through docling-serve health endpoint
            health_url = f"https://{pod_id}-5001.proxy.runpod.net/health"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    health_data = response.json()
                    
                    # Check if CUDA info is available in health response
                    cuda_info = health_data.get('cuda', {})
                    if cuda_info:
                        logger.info(f"✅ CUDA detected: {cuda_info}")
                        return True
                    else:
                        logger.warning("⚠️ No CUDA info in health response")
                        
                        # Try to get more detailed system info
                        try:
                            system_url = f"https://{pod_id}-5001.proxy.runpod.net/v1/system/info"
                            system_response = await client.get(system_url)
                            if system_response.status_code == 200:
                                system_data = system_response.json()
                                logger.info(f"📊 System info: {system_data}")
                        except:
                            pass
                        
                        return False
                else:
                    logger.error(f"❌ Health check failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error verifying CUDA: {e}")
            return False

    async def wait_for_pod_ready(self, pod_id: str, timeout: int = 600) -> Dict[str, Any]:
        """Wait for pod to be ready with longer timeout for processing pods"""
        
        start_time = now_cst()
        check_count = 0
        logger.info(f"⏳ Waiting for pod {pod_id} to be ready...")
        logger.info(f"⏰ Will check every 15 seconds for {timeout//60} minutes")
        logger.info("🚨 WILL NOT PROCEED UNTIL POD STATUS = RUNNING AND DOCLING-SERVE HEALTHY")
        
        while duration_since_cst(start_time) < timeout:
            check_count += 1
            elapsed = duration_since_cst(start_time)
            remaining = timeout - elapsed
            
            logger.info(f"\n🔍 STATUS CHECK #{check_count} (elapsed: {elapsed}s, remaining: {remaining}s)")
            
            try:
                response = await self.http_client.get(f"{self.runpod_base_url}/pods/{pod_id}")
                response.raise_for_status()
                
                pod_status = response.json()
                desired_status = pod_status.get('desiredStatus')
                machine_id = pod_status.get('machineId', 'Unknown')
                
                logger.info(f"📊 Current Status: {desired_status}")
                logger.info(f"🏭 Machine ID: {machine_id}")
                
                if desired_status == "RUNNING":
                    logger.info("🎉 POD IS NOW RUNNING!")
                    
                    # Pod is running, now check if docling-serve is healthy
                    health_url = f"https://{pod_id}-5001.proxy.runpod.net/health"
                    logger.info(f"🔍 Testing docling-serve health: {health_url}")
                    
                    try:
                        health_client = httpx.AsyncClient(timeout=30.0)
                        health_response = await health_client.get(health_url)
                        await health_client.aclose()
                        
                        if health_response.status_code == 200:
                            logger.info(f"✅ Pod {pod_id} is ready and docling-serve is healthy!")
                            
                            # Verify CUDA availability
                            cuda_available = await self.verify_cuda_availability(pod_id)
                            if cuda_available:
                                logger.info("✅ CUDA ACCELERATION CONFIRMED!")
                                logger.info("✅ READY TO PROCEED TO PROCESSING!")
                            else:
                                logger.warning("⚠️ CUDA not detected - processing may be slower")
                                logger.info("✅ READY TO PROCEED TO PROCESSING!")
                            
                            return {
                                "success": True,
                                "ready": True,
                                "pod_status": pod_status,
                                "pod_id": pod_id,
                                "cuda_available": cuda_available
                            }
                        else:
                            logger.info(f"⏳ Pod running but docling-serve not healthy yet: {health_response.status_code}")
                    except Exception as e:
                        logger.info(f"⏳ Pod running but docling-serve not accessible yet: {e}")
                elif desired_status == "FAILED":
                    logger.error(f"❌ Pod {pod_id} failed to start")
                    return {"success": False, "ready": False, "error": "Pod failed to start"}
                elif desired_status == "STARTING":
                    logger.info("🚀 Pod is starting up...")
                elif desired_status == "PENDING":
                    logger.info("⏳ Pod is pending...")
                else:
                    logger.info(f"⏳ Pod status: {desired_status}")
                
                logger.info("⏳ NOT READY YET - WAITING 15 seconds before next check...")
                
                # Wait before checking again
                await asyncio.sleep(15)
                
            except Exception as e:
                logger.error(f"❌ Error checking pod status: {e}")
                await asyncio.sleep(10)
        
        logger.error(f"⏰ Timeout waiting for pod {pod_id}")
        return {"success": False, "ready": False, "error": "Timeout waiting for pod"}

    async def get_pending_documents(self, limit: int = 50) -> List[Dict]:
        """Get documents pending processing from database"""
        
        query = """
        SELECT document_id, minio_object_key, original_filename, document_title, file_size_bytes
        FROM db_state 
        WHERE download_status = 'completed' 
        AND (serialization_status = 'pending' OR serialization_status IS NULL)
        AND minio_object_key IS NOT NULL
        ORDER BY created_at ASC
        LIMIT :limit
        """
        
        try:
            with self.db_service.engine.begin() as conn:
                from sqlalchemy import text
                result = conn.execute(text(query), {'limit': limit})
                rows = result.fetchall()
                
                # Convert to dictionaries manually to ensure compatibility
                documents = []
                for row in rows:
                    doc_dict = {
                        'document_id': row[0],
                        'minio_object_key': row[1], 
                        'original_filename': row[2],
                        'document_title': row[3],
                        'file_size_bytes': row[4]
                    }
                    documents.append(doc_dict)
                
                return documents
        except Exception as e:
            logger.error(f"❌ Error getting pending documents: {e}")
            return []

    async def download_from_minio(self, minio_key: str) -> Optional[bytes]:
        """Download file from MinIO raw bucket"""
        
        try:
            response = self.minio_manager.client.get_object(self.minio_manager.base_bucket, minio_key)
            return response.read()
        except Exception as e:
            logger.error(f"❌ Error downloading {minio_key}: {e}")
            return None

    async def process_document_with_clean_api(self, doc_info: Dict) -> bool:
        """Process a single document using clean docling API and save by filetype"""
        
        # Use content_hash as primary identifier in new system
        content_hash = doc_info['content_hash']
        filename = doc_info['filename']  # This is the full filename including content hash
        title = doc_info.get('canonical_title', 'Unknown')
        
        logger.info(f"📄 Processing document {content_hash[:16]}...: {title}")
        
        try:
            # Update status to processing in the new documents table
            with self.db_service.engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(text("""
                    UPDATE documents 
                    SET serialization_status = 'processing', updated_at = CURRENT_TIMESTAMP
                    WHERE content_hash = :content_hash
                """), {'content_hash': content_hash})
            
            # Download file from MinIO using new path structure: libhub/pdf/filename
            minio_path = f"pdf/{filename}"
            file_data = await self.download_from_minio(minio_path)
            if not file_data:
                raise Exception(f"Failed to download file from MinIO: {minio_path}")
            
            # Filename is already the full content-hash filename
            logger.info(f"📁 Downloaded {filename} from MinIO")
            
            # Process with clean docling-serve API
            result = await self.docling_api.process_file_with_base64(filename, file_data)
            if not result:
                raise Exception("Docling processing failed")
            
            # Extract document formats from result
            document = result.get('document', {})
            if not document:
                raise Exception("No document content in result")
            
            # Save all formats to appropriate MinIO buckets by filetype
            # Use content hash and canonical title from doc_info
            saved_urls = await self.minio_manager.save_document_by_filetype(content_hash, title, document)
            
            if not saved_urls:
                raise Exception("Failed to save any formats")
            
            # Update database with success status in new documents table
            with self.db_service.engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(text("""
                    UPDATE documents 
                    SET serialization_status = 'serialized',
                        serialization_timestamp = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE content_hash = :content_hash
                """), {'content_hash': content_hash})
            
            # Log the URLs for reference
            logger.info(f"📁 Saved URLs: {json.dumps(saved_urls, indent=2)}")
            
            logger.info(f"✅ Successfully processed document {content_hash[:16]}...")
            logger.info(f"📊 Saved formats: {list(saved_urls.keys())}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to process document {content_hash[:16]}...: {e}")
            
            # Update database with failure status in new documents table
            with self.db_service.engine.begin() as conn:
                from sqlalchemy import text
                conn.execute(text("""
                    UPDATE documents 
                    SET serialization_status = 'failed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE content_hash = :content_hash
                """), {'content_hash': content_hash})
            
            # Log the error for reference
            logger.error(f"💥 Error details: {str(e)}")
            
            return False

    async def process_batch_in_pod(self, pod_id: str, batch_size: int = 10) -> Dict[str, Any]:
        """Process a batch of documents within the pod environment"""
        
        logger.info(f"🔄 Starting batch processing in pod {pod_id}")
        
        # Get pending documents
        pending_docs = await self.get_pending_documents(batch_size)
        
        if not pending_docs:
            logger.info("📭 No pending documents found")
            return {"processed": 0, "failed": 0, "total": 0}
        
        logger.info(f"📋 Found {len(pending_docs)} documents to process")
        
        # Initialize MinIO bucket
        await self.minio_manager.ensure_base_bucket()
        
        # Process documents
        results = {"processed": 0, "failed": 0, "total": len(pending_docs)}
        
        for doc_info in pending_docs:
            success = await self.process_document_with_clean_api(doc_info)
            if success:
                results["processed"] += 1
            else:
                results["failed"] += 1
        
        logger.info(f"📊 Batch complete: {results}")
        return results

    async def complete_processing_workflow(self, batch_size: int = 10) -> Dict[str, Any]:
        """Complete workflow: create pod → process batch → cleanup"""
        
        logger.info("🚀 Starting complete processing workflow")
        
        workflow_start = now_cst()
        pod_id = None
        
        try:
            # Step 1: Check if there are documents to process
            pending_count = len(await self.get_pending_documents(batch_size))
            if pending_count == 0:
                return {
                    "status": "success",
                    "message": "No documents pending processing",
                    "pending_docs": 0
                }
            
            logger.info(f"📊 Found {pending_count} documents to process")
            
            # Step 2: Create pod with full environment for processing
            pod_result = await self.create_processing_pod(include_env=True)
            if not pod_result.get('success'):
                raise Exception(f"Failed to create pod: {pod_result.get('error')}")
            
            pod_id = pod_result['pod_id']
            pod_data = pod_result['pod_data']
            
            # Step 3: Wait for pod to be ready
            ready_result = await self.wait_for_pod_ready(pod_id)
            if not ready_result.get('success'):
                raise Exception(f"Pod not ready: {ready_result.get('error')}")
            
            # Step 4: Process batch
            processing_results = await self.process_batch_in_pod(pod_id, batch_size)
            
            # Step 5: Cleanup
            await self.stop_pod(pod_id)
            await asyncio.sleep(5)
            await self.delete_pod(pod_id)
            
            total_duration = duration_since_cst(workflow_start)
            
            return {
                "status": "success",
                "pod_id": pod_id,
                "total_processed": processing_results["processed"],
                "total_failed": processing_results["failed"],
                "total_documents": processing_results["total"],
                "duration_seconds": total_duration,
                "cost_estimate": f"${pod_data.get('costPerHr', 0) * (total_duration / 3600):.4f}"
            }
            
        except Exception as e:
            logger.error(f"❌ Workflow failed: {e}")
            
            # Cleanup on failure
            if pod_id:
                try:
                    await self.stop_pod(pod_id)
                    await asyncio.sleep(5)
                    await self.delete_pod(pod_id)
                except:
                    pass
            
            return {
                "status": "failed",
                "error": str(e),
                "pod_id": pod_id,
                "duration": duration_since_cst(workflow_start)
            }

    async def stop_pod(self, pod_id: str) -> Dict[str, Any]:
        """Stop a running pod"""
        
        try:
            logger.info(f"🛑 Stopping pod: {pod_id}")
            
            response = await self.http_client.post(f"{self.runpod_base_url}/pods/{pod_id}/stop")
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Pod stopped: {pod_id}")
            
            return {"success": True, "result": result}
            
        except Exception as e:
            logger.error(f"❌ Failed to stop pod {pod_id}: {e}")
            return {"success": False, "error": str(e)}

    async def delete_pod(self, pod_id: str) -> Dict[str, Any]:
        """Delete a pod"""
        
        try:
            logger.info(f"🗑️ Deleting pod: {pod_id}")
            
            response = await self.http_client.delete(f"{self.runpod_base_url}/pods/{pod_id}")
            response.raise_for_status()
            
            # Remove from active pods list
            if pod_id in self.active_pods:
                self.active_pods.remove(pod_id)
            
            logger.info(f"✅ Pod deleted: {pod_id}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"❌ Failed to delete pod {pod_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics"""
        
        try:
            with self.db_service.engine.begin() as conn:
                from sqlalchemy import text
                
                # Status breakdown
                result = conn.execute(text("""
                    SELECT processing_status, COUNT(*) as count
                    FROM db_state 
                    GROUP BY processing_status
                """))
                status_counts = {row[0]: row[1] for row in result.fetchall()}
                
                # Recent activity
                result = conn.execute(text("""
                    SELECT COUNT(*) as recent_processed
                    FROM db_state 
                    WHERE processing_status = 'serialized' 
                    AND serialization_timestamp > NOW() - INTERVAL '1 hour'
                """))
                recent_processed = result.fetchone()[0]
                
                return {
                    "status_breakdown": status_counts,
                    "recent_processed_1h": recent_processed,
                    "active_pods": len(self.active_pods),
                    "filetype_folders": list(self.minio_manager.folder_mapping.values()),
                    "timestamp": format_cst_iso()
                }
                    
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"error": str(e)}

    async def cleanup(self):
        """Cleanup all resources"""
        try:
            await self.http_client.aclose()
            await self.docling_api.client.aclose()
        except:
            pass


# Convenience functions for the data processor
async def trigger_runpod_batch_processing(batch_size: int = 10) -> Dict[str, Any]:
    """Trigger complete RunPod batch processing workflow"""
    service = RunPodDoclingService()
    try:
        return await service.complete_processing_workflow(batch_size)
    finally:
        await service.cleanup()


async def get_runpod_processing_stats() -> Dict[str, Any]:
    """Get current processing statistics"""
    service = RunPodDoclingService()
    try:
        return await service.get_processing_stats()
    finally:
        await service.cleanup()


# Legacy functions for compatibility
async def trigger_cloud_processing(max_batch_size: Optional[int] = None) -> Dict[str, Any]:
    """Legacy function - redirects to new implementation"""
    return await trigger_runpod_batch_processing(max_batch_size or 10)


async def check_runpod_status() -> Dict[str, Any]:
    """Check RunPod processing capability"""
    api_key = os.getenv('RUNPOD_API_KEY')
    return {
        "available": bool(api_key),
        "api_key_configured": bool(api_key),
        "template_id": os.getenv('RUNPOD_TEMPLATE_ID', 'fv9ha2jppg'),
        "clean_api_enabled": True,
        "filetype_organization": True
    }