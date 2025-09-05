import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json
from src.services.pdf_processor import pdf_processor
from typing import Optional, Any

def process_pdf_task(pdf_data: bytes, filename: str, file_hash: Optional[str] = None, **_extra_kwargs: Any):
    """
    Task to process PDF asynchronously (compatible with simulated queue system)
    """
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    
    try:
        # Save uploaded file
        pdf_path = temp_path / filename
        with open(pdf_path, "wb") as f:
            f.write(pdf_data)
        
        # Process the PDF
        print(f"📄 Processing {filename} in async task")
        # process_pdf returns a tuple: (doc, method)
        doc, method = pdf_processor.process_pdf(pdf_path)
        
        # Generate results
        pdf_stem = pdf_path.stem
        results = pdf_processor.get_output(doc, pdf_stem, "ocr")
        
        if results:
            print(f"✅ Successfully processed {filename} in async task")
            return {
                "status": "success",
                "filename": filename,
                "conversion_method": method,
                "files": results
            }
        else:
            raise Exception("Failed to create output files")
            
    except Exception as e:
        error_msg = f"Async task error for {filename}: {e}"
        print(f"❌ {error_msg}")
        raise e
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_path)
        except Exception as e:
            print(f"⚠️ Error cleaning up temp directory: {e}")
