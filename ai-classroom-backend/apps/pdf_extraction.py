"""
Robust PDF extraction pipeline with intelligent fallback handling.
Tries multiple extraction methods and falls back gracefully.
"""
import logging
from typing import Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod
from enum import Enum
import io

logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Enum for extraction methods with priority."""
    PYPDFIUM2 = ("pypdfium2", 100)  # Best quality
    PDFPLUMBER = ("pdfplumber", 80)
    OCR = ("ocr", 60)  # RapidOCR for scanned PDFs
    FALLBACK_HASH = ("hash", 10)  # Final fallback
    
    def __init__(self, name: str, quality_score: int):
        self.method_name = name
        self.quality_score = quality_score


class PDFExtractor(ABC):
    """Base class for PDF extractors."""
    
    @abstractmethod
    def extract(self, file_obj) -> Dict[str, Any]:
        """
        Extract text from PDF.
        
        Returns:
            {
                "success": bool,
                "text": str,
                "pages": int,
                "quality_score": int,
                "method": str,
                "error": str (if failed),
            }
        """
        pass


class Pypdfium2Extractor(PDFExtractor):
    """Extract using pypdfium2 (fastest, best quality)."""
    
    def extract(self, file_obj) -> Dict[str, Any]:
        try:
            import pypdfium2 as pdfium
            
            # Read file into bytes
            file_obj.seek(0)
            pdf_data = file_obj.read()
            file_obj.seek(0)
            
            # Open PDF
            pdf = pdfium.PdfDocument.new_from_in_memory(pdf_data)
            
            text_parts = []
            page_count = len(pdf)
            
            # Extract from each page
            for page_num in range(page_count):
                try:
                    page = pdf.get_page(page_num)
                    text = page.get_textpage().get_text()
                    text_parts.append(text)
                except Exception as e:
                    logger.warning(f"Failed to extract page {page_num}: {str(e)}")
                    continue
            
            full_text = "\n\n".join(text_parts)
            
            return {
                "success": True,
                "text": full_text,
                "pages": page_count,
                "quality_score": ExtractionMethod.PYPDFIUM2.quality_score,
                "method": "pypdfium2",
            }
        
        except Exception as e:
            logger.error(f"Pypdfium2 extraction failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "method": "pypdfium2",
            }


class PdfplumberExtractor(PDFExtractor):
    """Extract using pdfplumber (good for tables)."""
    
    def extract(self, file_obj) -> Dict[str, Any]:
        try:
            import pdfplumber
            
            file_obj.seek(0)
            
            with pdfplumber.open(file_obj) as pdf:
                text_parts = []
                page_count = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    except Exception as e:
                        logger.warning(f"Failed to extract page {page_num}: {str(e)}")
                        continue
            
            full_text = "\n\n".join(text_parts)
            
            if not full_text.strip():
                return {
                    "success": False,
                    "error": "No text extracted from PDF",
                    "method": "pdfplumber",
                }
            
            return {
                "success": True,
                "text": full_text,
                "pages": page_count,
                "quality_score": ExtractionMethod.PDFPLUMBER.quality_score,
                "method": "pdfplumber",
            }
        
        except Exception as e:
            logger.error(f"Pdfplumber extraction failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "method": "pdfplumber",
            }


class OCRExtractor(PDFExtractor):
    """Extract using RapidOCR for scanned PDFs."""
    
    def extract(self, file_obj) -> Dict[str, Any]:
        try:
            from pdf2image import convert_from_bytes
            from rapidocr_onnxruntime import RapidOCR
            
            file_obj.seek(0)
            pdf_data = file_obj.read()
            file_obj.seek(0)
            
            # Convert PDF pages to images
            images = convert_from_bytes(pdf_data, dpi=150)
            
            # Initialize OCR
            ocr = RapidOCR()
            
            text_parts = []
            page_count = len(images)
            
            for page_num, image in enumerate(images):
                try:
                    # Run OCR on image
                    results, _ = ocr(image)
                    
                    if results:
                        # Extract text from OCR results
                        page_text = "\n".join([line[1] for line in results])
                        text_parts.append(page_text)
                except Exception as e:
                    logger.warning(f"OCR failed for page {page_num}: {str(e)}")
                    continue
            
            full_text = "\n\n".join(text_parts)
            
            if not full_text.strip():
                return {
                    "success": False,
                    "error": "No text extracted via OCR",
                    "method": "ocr",
                }
            
            return {
                "success": True,
                "text": full_text,
                "pages": page_count,
                "quality_score": ExtractionMethod.OCR.quality_score,
                "method": "ocr",
            }
        
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "method": "ocr",
            }


class FallbackExtractor(PDFExtractor):
    """Final fallback: extract basic metadata."""
    
    def extract(self, file_obj) -> Dict[str, Any]:
        try:
            import pypdf
            
            file_obj.seek(0)
            reader = pypdf.PdfReader(file_obj)
            
            text_parts = []
            page_count = len(reader.pages)
            
            for page in reader.pages:
                try:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception:
                    pass
            
            full_text = "\n\n".join(text_parts) if text_parts else "[PDF extracted via basic fallback]"
            
            return {
                "success": True,
                "text": full_text,
                "pages": page_count,
                "quality_score": ExtractionMethod.FALLBACK_HASH.quality_score,
                "method": "fallback",
            }
        
        except Exception as e:
            logger.error(f"Fallback extraction failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "method": "fallback",
            }


class PDFExtractionPipeline:
    """
    Intelligent PDF extraction pipeline with fallback handling.
    Tries multiple extraction methods in priority order.
    """
    
    # Extraction methods in priority order
    EXTRACTORS = [
        ("pypdfium2", Pypdfium2Extractor()),
        ("pdfplumber", PdfplumberExtractor()),
        ("ocr", OCRExtractor()),
        ("fallback", FallbackExtractor()),
    ]
    
    def __init__(self, max_extraction_attempts: int = 3, min_quality_score: int = 30):
        """
        Initialize pipeline.
        
        Args:
            max_extraction_attempts: Maximum methods to try
            min_quality_score: Minimum quality score to accept
        """
        self.max_attempts = max_extraction_attempts
        self.min_quality_score = min_quality_score
        self.extraction_history = []
    
    def extract(self, file_obj, filename: str = "") -> Dict[str, Any]:
        """
        Extract text from PDF using intelligent fallback.
        
        Args:
            file_obj: Django file object or file-like object
            filename: Optional filename for logging
            
        Returns:
            {
                "success": bool,
                "text": str,
                "pages": int,
                "quality_score": int,
                "method": str,
                "attempts": list,  # All attempted methods
                "error": str (if failed),
            }
        """
        self.extraction_history = []
        
        logger.info(f"Starting PDF extraction pipeline for {filename}")
        
        attempts_made = 0
        best_result = None
        best_quality = -1
        
        # Try each extraction method
        for method_name, extractor in self.EXTRACTORS[:self.max_attempts]:
            try:
                logger.debug(f"Attempting extraction with {method_name}")
                
                # Reset file position
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
                
                result = extractor.extract(file_obj)
                self.extraction_history.append({
                    "method": method_name,
                    "success": result.get("success", False),
                    "quality_score": result.get("quality_score", 0),
                    "error": result.get("error"),
                })
                
                attempts_made += 1
                
                if result.get("success"):
                    quality = result.get("quality_score", 0)
                    
                    logger.info(
                        f"Extraction successful with {method_name} "
                        f"(quality: {quality}, pages: {result.get('pages')})"
                    )
                    
                    # Track best result
                    if quality > best_quality:
                        best_quality = quality
                        best_result = result
                    
                    # If quality is acceptable, return it
                    if quality >= self.min_quality_score:
                        return {
                            **result,
                            "attempts": self.extraction_history,
                        }
                    
            except Exception as e:
                logger.error(f"Exception during {method_name} extraction: {str(e)}")
                self.extraction_history.append({
                    "method": method_name,
                    "success": False,
                    "error": str(e),
                })
                attempts_made += 1
        
        # Return best result if we have one
        if best_result:
            logger.warning(f"Returning best result from {best_result['method']} (quality: {best_quality})")
            return {
                **best_result,
                "attempts": self.extraction_history,
            }
        
        # All methods failed
        logger.error(f"All extraction methods failed for {filename}")
        
        return {
            "success": False,
            "text": "",
            "pages": 0,
            "quality_score": 0,
            "method": None,
            "attempts": self.extraction_history,
            "error": "All extraction methods failed",
        }
    
    def get_extraction_summary(self) -> Dict[str, Any]:
        """Get summary of extraction attempts."""
        successful_attempts = [a for a in self.extraction_history if a.get("success")]
        
        return {
            "total_attempts": len(self.extraction_history),
            "successful_attempts": len(successful_attempts),
            "best_method": best_method if (best_method := max(
                (a for a in successful_attempts),
                key=lambda x: x.get("quality_score", 0),
                default=None
            )) else None,
            "history": self.extraction_history,
        }
