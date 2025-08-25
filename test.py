from src.services.pdf_processor import PDFProcessor
from pathlib import Path
from docling_core.types.doc.base import (
    ImageRefMode,
)
processor = PDFProcessor()

doc = processor.process_pdf(Path("warmup_files/test1.pdf"))

print(doc.export_to_markdown(image_mode=ImageRefMode.EMBEDDED))
print("--------------------------------")
print(doc.export_to_html(image_mode=ImageRefMode.EMBEDDED))
print("--------------------------------")

print("--------------------------------")

print(doc.export_to_doctags())
print("--------------------------------")
print(doc.export_to_dict())
print("--------------------------------")


print(doc.export_to_doctags() == doc.export_to_dict())

