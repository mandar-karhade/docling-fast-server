import tempfile
import shutil
import asyncio
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from src.services.pdf_processor import pdf_processor
from src.services.queue_manager import queue_manager
from src.models.job import JobUpdate

router = APIRouter()


@router.post("/ocr")
async def process_pdf_ocr(file: UploadFile = File(...)):
    """Process PDF file and return zip with OCR results"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    
    try:
        # Save uploaded file
        pdf_path = temp_path / file.filename
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process the PDF
        doc = pdf_processor.process_pdf(pdf_path, temp_path)
        
        # Generate results directly from document
        pdf_stem = pdf_path.stem
        results = pdf_processor.get_output(doc, pdf_stem, "ocr")
        
        if results:
            # Clean up the temporary directory
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            
            # Return JSON response with all content (will be automatically compressed)
            return {
                "status": "success",
                "filename": file.filename,
                "files": results
            }
        else:
            # Clean up on failure
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            raise HTTPException(status_code=500, detail="Failed to create output files")
                
    except Exception as e:
        print(f"❌ Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/ocr/async")
async def process_pdf_ocr_async(file: UploadFile = File(...)):
    """Process PDF file asynchronously using RQ and return RQ job ID"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Submit job to RQ queue
        from src.services.rq_tasks import process_pdf_task
        rq_job = queue_manager.enqueue_job(
            process_pdf_task,
            args=(file_content, file.filename),
            job_timeout='1h',  # 1 hour timeout
            result_ttl=3600,   # Keep result for 1 hour
            failure_ttl=3600   # Keep failed jobs for 1 hour
        )
        
        return {
            "status": "accepted",
            "job_id": rq_job.id,  # Use RQ job ID as primary identifier
            "batch_id": queue_manager._get_current_batch_id(),
            "message": "PDF processing queued. Use /jobs/{job_id} to check status."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {str(e)}")


async def process_pdf_async(job_id: str, pdf_path: Path, temp_path: Path):
    """Process PDF asynchronously and update job status"""
    # Set task name for tracking
    current_task = asyncio.current_task()
    if current_task:
        current_task.set_name(f"process_pdf_{job_id}")
    
    try:
        # Mark job as active and not waiting
        update = JobUpdate(status="processing", active=True, waiting=False)
        queue_manager.update_job(job_id, update, "Job started processing")
        
        # Get queue info before starting
        queue_info = queue_manager.get_worker_queue_info()
        queue_manager.update_job(job_id, JobUpdate(), f"Queue status: {queue_info}")
        
        # Process the PDF in a thread pool since process_pdf is blocking
        queue_manager.update_job(job_id, JobUpdate(), "Starting document conversion in thread pool")
        loop = asyncio.get_event_loop()
        doc = await loop.run_in_executor(None, pdf_processor.process_pdf, pdf_path, temp_path)
        queue_manager.update_job(job_id, JobUpdate(), "Document conversion completed")
        
        # Generate results
        queue_manager.update_job(job_id, JobUpdate(), "Generating output formats")
        pdf_stem = pdf_path.stem
        results = pdf_processor.get_output(doc, pdf_stem, "ocr")
        queue_manager.update_job(job_id, JobUpdate(), "Output generation completed")
        
        if results:
            result_data = {
                "status": "success",
                "filename": pdf_path.name,
                "files": results
            }
            update = JobUpdate(status="completed", active=False, waiting=False, result=result_data)
            queue_manager.update_job(job_id, update, "Job completed successfully")
        else:
            update = JobUpdate(status="failed", active=False, waiting=False, error="Failed to create output files")
            queue_manager.update_job(job_id, update, "Failed to create output files")
            
    except Exception as e:
        error_msg = f"Async processing error for job {job_id}: {e}"
        print(f"❌ {error_msg}")
        update = JobUpdate(status="failed", active=False, waiting=False, error=str(e))
        queue_manager.update_job(job_id, update, error_msg)
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_path)
            queue_manager.update_job(job_id, JobUpdate(), "Temporary directory cleaned up")
        except Exception as e:
            queue_manager.update_job(job_id, JobUpdate(), f"Error cleaning up temp directory: {e}")
