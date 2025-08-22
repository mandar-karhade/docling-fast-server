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
    return PdfPipelineOptions(
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

app = FastAPI(
    title="Docling API",
    description="API for processing PDFs using Docling",
    version="1.0.0"
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

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
