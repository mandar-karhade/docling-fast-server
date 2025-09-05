import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse

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
async def process_pdf_ocr_async(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    request_id: str | None = Form(default=None),
):
    """Process PDF file asynchronously using RQ and return RQ job ID"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        # Determine canonical job_id (request_id is deprecated alias)
        client_job_id = job_id or request_id

        # If client provided a job_id (or alias), enforce uniqueness and use it
        if client_job_id:
            # Check existence irrespective of deployment by asking the job store directly
            existing = queue_manager.job_store.get_job(client_job_id)
            if existing:
                return JSONResponse(status_code=409, content={"job_id": client_job_id})

        # Read file content
        file_content = await file.read()

        # Submit job to queue
        from src.services.rq_tasks import process_pdf_task

        enqueue_kwargs = dict(
            job_timeout='1h',
            result_ttl=3600,
            failure_ttl=3600,
        )
        if client_job_id:
            enqueue_kwargs['job_id'] = client_job_id

        rq_job = queue_manager.enqueue_job(
            process_pdf_task,
            file_content,
            file.filename,
            **enqueue_kwargs,
        )

        return {"job_id": rq_job.id}
        
    except HTTPException:
        # Propagate intended HTTP errors (e.g., 409 duplicate)
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {str(e)}")



