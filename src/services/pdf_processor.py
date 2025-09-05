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
    EasyOcrOptions,
)
from docling_core.types.doc.base import (
    ImageRefMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions

# Chunking imports
from docling.chunking import HybridChunker

# Load environment
load_dotenv()
OMP_NUM_THREADS = os.getenv('OMP_NUM_THREADS', 4)

print(f"OpenAI API Key available: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")


class PDFProcessor:
    def __init__(self):
        self.picture_type = 'openai'  # You can make this configurable
        # Initialize chunker (lazy loading)
        self._chunker = None
    
    def _initialize_chunker(self):
        """Initialize the hybrid chunker (lazy loading)"""
        if self._chunker is None:
            print("🔧 Initializing hybrid chunker...")
            self._chunker = HybridChunker()
            print("✅ Hybrid chunker initialized")
        return self._chunker

    def create_hybrid_chunks(self, doc, pdf_stem: str, suffix: str) -> Dict[str, Any]:
        """Create hybrid chunks from document using HybridChunker"""
        try:
            print(f"🔧 Starting hybrid chunking for {pdf_stem}_{suffix}")
            chunker = self._initialize_chunker()
            chunks = list(chunker.chunk(dl_doc=doc))
            
            # Create chunks data structure
            chunks_data = {
                "content": doc.export_to_dict(),
                "chunks": chunks
            }
            
            print(f"✅ Created {len(chunks)} chunks for {pdf_stem}_{suffix}")
            return chunks_data
            
        except Exception as chunk_error:
            print(f"⚠️ Error during chunking for {pdf_stem}_{suffix}: {chunk_error}")
            import traceback
            traceback.print_exc()
            # Return error structure
            return {
                "content": doc.export_to_dict(),
                "chunks": [],
                "error": str(chunk_error)
            }

    def get_picture_description_options(self) -> PictureDescriptionApiOptions:
        """Get picture description API options"""
        if self.picture_type == 'openai':
            # Configure picture description API (same as docling-serve)
            picture_description_options = PictureDescriptionApiOptions(
                url="https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                    "Content-Type": "application/json"
                },
                params={
                    "model": "gpt-4o-mini",
                    "max_completion_tokens": 300,
                    "temperature": 0.0
                },
                timeout=60,
                prompt="Describe this image in detail, including any text, tables, charts, or diagrams you can see."
            )
            return picture_description_options
        else:
            raise ValueError(f"Invalid picture description type: {self.picture_type}")

    def get_accelerator_options(self) -> AcceleratorOptions:
        """Get accelerator options"""
        # Use environment variable for thread count, default to 8
        num_threads = int(os.getenv('OMP_NUM_THREADS', 8))
        return AcceleratorOptions(
            num_threads=num_threads,
            device=AcceleratorDevice.AUTO,
        )

    def get_ocr_options(self) -> EasyOcrOptions:
        """Get OCR options"""
        return EasyOcrOptions(
            lang=['en'],  # 'latin' is not supported, using only 'en'
            #force_ocr=False,
            use_gpu=False,
            force_full_page_ocr=False,
            confidence_threshold=0.5,
            #model_storage_directory,
            download_enabled=True,
            # model_config = ConfigDict(
            # extra="forbid",
            # protected_namespaces=(),
            # )
        )

    def get_pdf_pipeline_options(self) -> PdfPipelineOptions:
        """Get PDF pipeline options."""
        return PdfPipelineOptions(
            # Accelerator options 
            accelerator_options=self.get_accelerator_options(),
            
            # OCR options
            do_ocr=True,
            force_ocr=False,    
            ocr_options=self.get_ocr_options(),

            # OCR enhancements
            table_mode="accurate",
            include_images=True,
            do_table_structure=True,
            do_code_enrichment=True,
            do_formula_enrichment=True,
            do_picture_classification=True,

            # external picture description API
            do_picture_description=True,
            enable_remote_services=True, 
            picture_description_options=self.get_picture_description_options(),
            generate_picture_images = True,
        )

    def get_pdf_pipeline_options_limited(self) -> PdfPipelineOptions:
        """Limited pipeline options with enrichment features disabled (for fallback tests)."""
        return PdfPipelineOptions(
            # Accelerator options
            accelerator_options=self.get_accelerator_options(),

            # OCR options
            do_ocr=True,
            force_ocr=False,
            ocr_options=self.get_ocr_options(),

            # Disable enrichment features
            table_mode="accurate",
            include_images=True,
            do_table_structure=False,
            do_code_enrichment=False,
            do_formula_enrichment=False,
            do_picture_classification=False,

            # Disable picture description and any remote services
            do_picture_description=False,
            enable_remote_services=False,
        )

    def process_pdf(self, pdf_path: Path):
        """Process PDF with default options; on idefics3 size error, retry with limited features.

        Returns a tuple: (docling_document, conversion_method) where conversion_method is
        "default" or "limited".
        """
        print(f"📄 Processing {pdf_path.name} with local docling")

        def build_converter(options: PdfPipelineOptions) -> DocumentConverter:
            return DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=options,
                    )
                }
            )

        # Attempt with default options
        default_opts = self.get_pdf_pipeline_options()
        print("🚀 Starting document conversion (default)...")
        try:
            result = build_converter(default_opts).convert(pdf_path)
            return result.document, "default"
        except Exception as e:
            msg = str(e)
            print(f"⚠️ Default conversion failed: {msg}")
            # Specific fallback for transformers image size constraint
            if ("resolution_max_side" in msg) and ("max_image_size" in msg):
                print("🔁 Retrying with limited pipeline features (tables/code/formula/pictures disabled)...")
                limited_opts = self.get_pdf_pipeline_options_limited()
                result = build_converter(limited_opts).convert(pdf_path)
                return result.document, "limited"
            # Propagate other errors
            raise

    def get_output(self, doc, pdf_stem: str, suffix: str) -> Dict[str, Any]:
        """Create results object from docling document without saving files"""
        try:
            # Create results object with all export formats
            results = {
                'filename': pdf_stem,
                'converted_doc': doc,
                'doctags': doc.export_to_doctags(),
                'json': doc.export_to_dict(),
                'markdown': doc.export_to_markdown(image_mode=ImageRefMode.EMBEDDED),
                'html': doc.export_to_html(image_mode=ImageRefMode.EMBEDDED),
                'chunks': self.create_hybrid_chunks(doc, pdf_stem, suffix)
            }
            
            print(f"📦 Created results object for {pdf_stem}_{suffix}")
            return results

        except Exception as e:
            print(f"❌ Error creating results for {pdf_stem}_{suffix}: {e}")
            import traceback
            traceback.print_exc()
            return None


    async def process_pdf_async(self, job_id: str, pdf_path: Path, temp_path: Path):
        """Process PDF asynchronously and update job status"""
        import asyncio
        import shutil
        from src.services.queue_manager import queue_manager
        from src.models.job import JobUpdate
        
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
            doc, method = await loop.run_in_executor(None, self.process_pdf, pdf_path)
            queue_manager.update_job(job_id, JobUpdate(), f"Document conversion completed (method={method})")
            
            # Generate results
            queue_manager.update_job(job_id, JobUpdate(), "Generating output formats")
            pdf_stem = pdf_path.stem
            results = self.get_output(doc, pdf_stem, "ocr")
            queue_manager.update_job(job_id, JobUpdate(), "Output generation completed")
            
            if results:
                result_data = {
                    "status": "success",
                    "filename": pdf_path.name,
                    "conversion_method": method,
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


# Global PDF processor instance
pdf_processor = PDFProcessor()
