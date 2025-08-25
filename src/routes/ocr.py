import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException

from src.services.pdf_processor import pdf_processor
from src.services.queue_manager import queue_manager

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
        doc = pdf_processor.process_pdf(pdf_path)
        
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
            file_content,  # First positional argument: PDF data
            file.filename,  # Second positional argument: filename
            job_timeout='1h',  # 1 hour timeout
            result_ttl=3600,   # Keep result for 1 hour
            failure_ttl=3600   # Keep failed jobs for 1 hour
        )
        
        return {
            "status": "accepted",
            "job_id": rq_job.id,  # Use RQ job ID as primary identifier
            "message": "PDF processing queued. Use /jobs/{job_id} to check status."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {str(e)}")



