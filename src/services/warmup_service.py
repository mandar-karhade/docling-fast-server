import os
import asyncio
import threading
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from src.services.ocr_service import OCRService


class WarmupService:
    def __init__(self):
        self.warmup_dir = Path("warmup_files")
        self.is_warmup_complete = False
        self.warmup_status = "not_started"
        self.warmup_results = []
        self.warmup_errors = []
        self.start_time = None
        self.end_time = None
        
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
            
            # Initialize OCR service (this will download models)
            ocr_service = OCRService()
            
            # Process each warmup file
            for i, pdf_file in enumerate(warmup_files, 1):
                try:
                    print(f"🔄 Processing warmup file {i}/{len(warmup_files)}: {pdf_file.name}")
                    
                    # Process the file
                    result = ocr_service.process_pdf(str(pdf_file))
                    
                    # Store result
                    self.warmup_results.append({
                        "file": pdf_file.name,
                        "status": "success",
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    print(f"✅ Warmup file {pdf_file.name} processed successfully")
                    
                except Exception as e:
                    error_msg = f"Error processing {pdf_file.name}: {str(e)}"
                    print(f"❌ {error_msg}")
                    self.warmup_errors.append({
                        "file": pdf_file.name,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
            
            # Mark warmup as complete
            self.warmup_status = "completed"
            self.is_warmup_complete = True
            self.end_time = datetime.now()
            
            print("🎉 Warmup process completed successfully!")
            
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
            "files_processed": len(self.warmup_results),
            "files_failed": len(self.warmup_errors)
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
