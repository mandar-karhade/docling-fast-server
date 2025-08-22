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

from docling_core.transforms.serializer.html import HTMLDocSerializer
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling_core.transforms.serializer.json import JSONDocSerializer
from docling_core.transforms.serializer.text import TextDocSerializer

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
                "max_tokens": 300
            },
            timeout=60,
            prompt="Describe this image in detail, including any text, tables, charts, or diagrams you can see."
        )
        return picture_description_options
    else:
        raise ValueError(f"Invalid picture description type: {picture_type}")


def get_accelerator_options():
    return AcceleratorOptions(
        num_threads=16,
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

def get_output(doc, output_dir: Path, pdf_stem: str, suffix: str, pdf_path: Path):
    """Save processed files from local docling result and return zip file path"""
    try:
        # Create output directory for this comparison
        comparison_dir = output_dir / f"{pdf_stem}_{suffix}"
        comparison_dir.mkdir(parents=True, exist_ok=True)
        
        # Save markdown
        markdown_file = comparison_dir / f"{pdf_stem}.md"
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(doc.export_to_markdown())
        print(f"💾 Saved markdown: {markdown_file}")
        
        # Save JSON
        json_file = comparison_dir / f"{pdf_stem}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(doc.export_to_dict(), f, indent=2)
        print(f"💾 Saved JSON: {json_file}")
        
        # Save HTML
        html_file = comparison_dir / f"{pdf_stem}.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(doc.export_to_html())
        print(f"💾 Saved HTML: {html_file}")
        
        # Save text
        text_file = comparison_dir / f"{pdf_stem}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(doc.export_to_text())
        print(f"💾 Saved text: {text_file}")
        
        # Create zip file
        import zipfile
        zip_path = output_dir / f"{pdf_stem}_{suffix}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in [markdown_file, json_file, html_file, text_file]:
                if file_path.exists():
                    zipf.write(file_path, file_path.name)
        
        print(f"📦 Created zip file: {zip_path}")
        return zip_path

    except Exception as e:
        print(f"❌ Error saving files for {pdf_stem}_{suffix}: {e}")
        import traceback
        traceback.print_exc()
        return None


# FastAPI Application
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import tempfile
import shutil

app = FastAPI(
    title="Docling API",
    description="API for processing PDFs using Docling",
    version="1.0.0"
)

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
    
    try:
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Save uploaded file
            pdf_path = temp_path / file.filename
            with open(pdf_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Process the PDF
            doc = process_pdf(pdf_path, temp_path)
            
            # Generate output files and zip
            pdf_stem = pdf_path.stem
            zip_path = get_output(doc, temp_path, pdf_stem, "ocr", pdf_path)
            
            if zip_path and zip_path.exists():
                return FileResponse(
                    path=str(zip_path),
                    media_type='application/zip',
                    filename=f"{pdf_stem}_ocr_results.zip"
                )
            else:
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
