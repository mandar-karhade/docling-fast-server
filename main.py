#!/usr/bin/env python3
"""
Simple Local Docling Test Script
================================
Use locally installed docling to process a single PDF with the same options.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Import docling components
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    PictureDescriptionApiOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

# These imports are not needed for the current implementation
# from docling_core.transforms.serializer.html import HTMLDocSerializer
# from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
# from docling_core.transforms.serializer.json import JSONDocSerializer
# from docling_core.transforms.serializer.text import TextDocSerializer

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions

# Load environment
load_dotenv()
OMP_NUM_THREADS = os.getenv('OMP_NUM_THREADS', 4)

print(f"OpenAI API Key available: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")

def get_picture_description_options():
    picture_type = 'openai'  # You can make this configurable
    if picture_type == 'openai':
        # Configure picture description API (same as docling-serve)
        picture_description_options = PictureDescriptionApiOptions(
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json"
            },
            params={
                "model": "gpt-5",
                "max_completion_tokens": 300
            },
            timeout=60,
            prompt="Describe this image in detail, including any text, tables, charts, or diagrams you can see."
        )
        return picture_description_options
    else:
        raise ValueError(f"Invalid picture description type: {picture_type}")


def get_accelerator_options():
    # Use environment variable for thread count, default to 8
    num_threads = int(os.getenv('OMP_NUM_THREADS', 8))
    return AcceleratorOptions(
        num_threads=num_threads,
        device=AcceleratorDevice.AUTO,
    )

def get_pdf_pipeline_options():
    # Set EasyOCR to use cached models
    artifacts_path = os.getenv('ARTIFACTS_PATH', '/workspace')
    os.environ['EASYOCR_MODULE_PATH'] = artifacts_path
    
    return PdfPipelineOptions(
                # Artifacts path for cached models
                artifacts_path=artifacts_path,
                
                # Accelerator options 
                accelerator_options = get_accelerator_options(),
                
                # OCR options
                do_ocr=True,
                force_ocr=False,
                table_mode="accurate",
                include_images=True,
                do_table_structure=True,
                do_code_enrichment=True,
                do_formula_enrichment=True,
                do_picture_classification=True,

                # external picture description API
                do_picture_description=True ,
                enable_remote_services=True, 
                picture_description_options = get_picture_description_options()
            )

def process_pdf(pdf_path: Path, output_dir: Path) -> Dict[str, Any]:
    """Process PDF using locally installed docling with the same options"""
    print(f"📄 Processing {pdf_path.name} with local docling")
    
    # Create document converter with PDF format options
    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=get_pdf_pipeline_options(),
            )
        }
    )
    
    print("🚀 Starting document conversion...")
    
    # Convert the document
    result = doc_converter.convert(pdf_path)
    return result.document

def get_output(doc, pdf_stem: str, suffix: str):
    """Create results object from docling document without saving files"""
    try:
        # Create results object with all export formats
        results = {
            'filename': pdf_stem,
            'converted_doc': doc,
            'markdown': doc.export_to_markdown(),
            'json': doc.export_to_dict(),
            'html': doc.export_to_html(),
            'text': doc.export_to_text()
        }
        
        print(f"📦 Created results object for {pdf_stem}_{suffix}")
        return results

    except Exception as e:
        print(f"❌ Error creating results for {pdf_stem}_{suffix}: {e}")
        import traceback
        traceback.print_exc()
        return None


# FastAPI Application
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
import tempfile
import shutil
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional

app = FastAPI(
    title="Docling API",
    description="API for processing PDFs using Docling",
    version="1.0.0"
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Job management
jobs: Dict[str, Dict] = {}

def create_job() -> str:
    """Create a new job and return job ID"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "progress": 0,
        "result": None,
        "error": None
    }
    return job_id

def update_job(job_id: str, status: str, progress: int = None, result: Dict = None, error: str = None):
    """Update job status and information"""
    if job_id in jobs:
        jobs[job_id]["status"] = status
        jobs[job_id]["updated_at"] = datetime.utcnow().isoformat()
        if progress is not None:
            jobs[job_id]["progress"] = progress
        if result is not None:
            jobs[job_id]["result"] = result
        if error is not None:
            jobs[job_id]["error"] = error

async def process_pdf_async(job_id: str, pdf_path: Path, temp_path: Path):
    """Process PDF asynchronously and update job status"""
    try:
        update_job(job_id, "processing", 10)
        
        # Process the PDF
        doc = process_pdf(pdf_path, temp_path)
        update_job(job_id, "processing", 50)
        
        # Generate results
        pdf_stem = pdf_path.stem
        results = get_output(doc, pdf_stem, "ocr")
        update_job(job_id, "processing", 90)
        
        if results:
            update_job(job_id, "completed", 100, {
                "status": "success",
                "filename": pdf_path.name,
                "files": results
            })
        else:
            update_job(job_id, "failed", error="Failed to create output files")
            
    except Exception as e:
        update_job(job_id, "failed", error=str(e))
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_path)
        except:
            pass

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "docling-api",
        "openai_key_available": bool(os.getenv('OPENAI_API_KEY'))
    }

@app.post("/ocr")
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
        doc = process_pdf(pdf_path, temp_path)
        
        # Generate results directly from document
        pdf_stem = pdf_path.stem
        results = get_output(doc, pdf_stem, "ocr")
        
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

@app.post("/ocr/async")
async def process_pdf_ocr_async(file: UploadFile = File(...)):
    """Start async PDF processing and return job ID"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create job
    job_id = create_job()
    
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    
    try:
        # Save uploaded file
        pdf_path = temp_path / file.filename
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Start async processing
        asyncio.create_task(process_pdf_async(job_id, pdf_path, temp_path))
        
        return {
            "status": "accepted",
            "job_id": job_id,
            "message": "PDF processing started. Use /jobs/{job_id} to check status."
        }
        
    except Exception as e:
        update_job(job_id, "failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "result": job["result"],
        "error": job["error"]
    }

@app.get("/jobs")
async def list_jobs():
    """List all jobs"""
    return {
        "jobs": [
            {
                "job_id": job_id,
                "status": job["status"],
                "progress": job["progress"],
                "created_at": job["created_at"],
                "updated_at": job["updated_at"]
            }
            for job_id, job in jobs.items()
        ]
    }

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del jobs[job_id]
    return {"status": "deleted", "job_id": job_id}

@app.post("/serialize")
async def serialize_endpoint():
    """Placeholder serialize endpoint"""
    return {"status": "success", "message": "Serialize endpoint - not implemented yet"}

@app.post("/chunk")
async def chunk_endpoint():
    """Placeholder chunk endpoint"""
    return {"status": "success", "message": "Chunk endpoint - not implemented yet"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
