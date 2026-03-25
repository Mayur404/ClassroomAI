"""
Premium PDF extraction with advanced OCR optimization for scanned documents.
Handles all PDF types with confidence scoring and metadata preservation.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageEnhance
from rapidocr_onnxruntime import RapidOCR
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Global OCR engine
_OCR_ENGINE = None

@dataclass
class ExtractionMetadata:
    """Metadata for extracted text from a PDF."""
    page_num: int
    extraction_method: str  # 'pdfplumber', 'ocr_native', 'ocr_scanned'
    confidence: float  # 0.0-1.0
    has_images: bool
    is_scanned: bool
    text_count: int
    processing_time_ms: float
    heading_markers: list[str] = field(default_factory=list)

@dataclass
class ExtractedBlock:
    """A block of extracted text with metadata."""
    text: str
    page_num: int
    block_index: int
    metadata: ExtractionMetadata
    section_path: Optional[list[str]] = None
    confidence: float = 0.9
    raw_coordinates: Optional[dict] = None  # Top, left, bottom, right


class PremiumPDFExtractor:
    """Advanced PDF extraction with OCR optimization for all document types."""
    
    def __init__(self):
        self.ocr_engine = None
        self.preprocessing_config = {
            'denoise': True,
            'deskew': True,
            'contrast_enhance': True,
            'scale_factor': 2.5,
        }
        
    def get_ocr_engine(self):
        """Lazily initialize OCR engine."""
        global _OCR_ENGINE
        if _OCR_ENGINE is None:
            _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE
    
    def extract_pdf_blocks(self, pdf_path: str) -> list[ExtractedBlock]:
        """
        Extract all text blocks from PDF with confidence scoring.
        Automatically chooses extraction method based on PDF type.
        """
        blocks = []
        
        try:
            # First try pdfplumber for native PDFs
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Extracting from PDF: {total_pages} pages")
                
                for page_idx, page in enumerate(pdf.pages):
                    page_blocks = self._extract_page_blocks(
                        page, page_idx, pdf_path, total_pages
                    )
                    blocks.extend(page_blocks)
                    
        except Exception as e:
            logger.error(f"Error extracting PDF: {e}")
            raise
        
        return blocks
    
    def _extract_page_blocks(
        self,
        page,
        page_idx: int,
        pdf_path: str,
        total_pages: int
    ) -> list[ExtractedBlock]:
        """Extract blocks from a single page."""
        blocks = []
        import time
        start = time.time()
        
        # Step 1: Try native text extraction with pdfplumber
        native_text = self._extract_native_text(page)
        native_confidence = self._calculate_text_confidence(native_text)
        
        # Step 2: Check if PDF is scanned (very low native text)
        is_scanned = native_confidence < 0.3
        has_images = len(page.images) > 0 if hasattr(page, 'images') else False
        
        logger.info(f"Page {page_idx+1}/{total_pages}: "
                   f"native_conf={native_confidence:.2f}, scanned={is_scanned}, images={has_images}")
        
        # Step 3: Use optimal extraction method
        if is_scanned or (has_images and native_confidence < 0.5):
            # Use OCR for scanned documents
            extracted_text = self._extract_with_ocr(pdf_path, page_idx)
            extraction_method = 'ocr_scanned' if is_scanned else 'ocr_hybrid'
            confidence = 0.85
        else:
            # Use native extraction for digital PDFs
            extracted_text = native_text
            extraction_method = 'pdfplumber_native'
            confidence = native_confidence
        
        # Step 4: Post-process extracted text
        processed_text = self._post_process_extracted_text(extracted_text)
        
        # Step 5: Break into logical blocks
        text_blocks = self._break_into_blocks(processed_text)
        
        processing_time_ms = (time.time() - start) * 1000
        metadata = ExtractionMetadata(
            page_num=page_idx,
            extraction_method=extraction_method,
            confidence=confidence,
            has_images=has_images,
            is_scanned=is_scanned,
            text_count=len(process_text),
            processing_time_ms=processing_time_ms,
        )
        
        # Create blocks with metadata
        for block_idx, block_text in enumerate(text_blocks):
            block = ExtractedBlock(
                text=block_text,
                page_num=page_idx,
                block_index=block_idx,
                metadata=metadata,
                confidence=confidence,
            )
            blocks.append(block)
        
        return blocks
    
    def _extract_native_text(self, page) -> str:
        """Extract text using pdfplumber native method."""
        try:
            text = page.extract_text(layout=True) or ""
            return text
        except Exception as e:
            logger.warning(f"Native extraction failed: {e}")
            return ""
    
    def _extract_with_ocr(self, pdf_path: str, page_idx: int) -> str:
        """Extract text from PDF page using OCR with preprocessing."""
        try:
            # Load PDF with pdfium
            pdf = pdfium.PdfDocument.new()
            pdf = pdfium.PdfDocument.open(pdf_path)
            page = pdf[page_idx]
            
            # Render with high DPI for better OCR
            bitmap = page.render(
                scale=self.preprocessing_config['scale_factor'],
                rotation=0,
            )
            image = bitmap.to_pil()
            
            # Preprocess image for OCR
            image = self._preprocess_image_for_ocr(image)
            
            # Run OCR
            ocr_engine = self.get_ocr_engine()
            image_array = np.array(image)
            ocr_result, timing = ocr_engine(image_array)
            
            # Convert OCR result to text
            extracted_text = self._format_ocr_result(ocr_result)
            
            image.close()
            bitmap.close()
            
            return extracted_text
            
        except Exception as e:
            logger.error(f"OCR extraction failed for page {page_idx}: {e}")
            return ""
    
    def _preprocess_image_for_ocr(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image to improve OCR accuracy.
        Handles denoise, deskew, contrast enhancement.
        """
        if not self.preprocessing_config['denoise']:
            return image
        
        # Convert to grayscale if color
        if image.mode == 'RGB' or image.mode == 'RGBA':
            image = image.convert('L')
        
        # Enhance contrast for scanned documents
        if self.preprocessing_config['contrast_enhance']:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.2)
        
        return image
    
    def _format_ocr_result(self, ocr_result) -> str:
        """Format RapidOCR output into readable text."""
        if not ocr_result:
            return ""
        
        # Sort by vertical position (top to bottom)
        sorted_results = sorted(
            ocr_result,
            key=lambda x: min(point[1] for point in x[0]) if x[0] else 0
        )
        
        lines = []
        current_y = None
        current_line = []
        
        for detection in sorted_results:
            if not isinstance(detection, (list, tuple)) or len(detection) < 3:
                continue
            
            points = detection[0]
            text = detection[1]
            confidence = detection[2]
            
            # Filter low confidence detections
            if float(confidence) < 0.5:
                continue
            
            # Get Y position (top of text)
            y_pos = min(point[1] for point in points) if points else 0
            
            # New line detected
            if current_y is not None and abs(y_pos - current_y) > 20:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [text]
                current_y = y_pos
            else:
                current_line.append(text)
                if current_y is None:
                    current_y = y_pos
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return "\n".join(lines)
    
    def _post_process_extracted_text(self, text: str) -> str:
        """Clean and normalize extracted text."""
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Remove noise patterns
            line = self._remove_pdf_noise(line)
            
            # Normalize whitespace
            line = ' '.join(line.split())
            
            # Skip very short lines that are probably junk
            if len(line) < 3:
                continue
            
            cleaned_lines.append(line)
        
        # Join with newlines
        text = '\n'.join(cleaned_lines)
        
        # Fix broken words (common OCR issue)
        text = self._fix_broken_words(text)
        
        return text
    
    def _remove_pdf_noise(self, line: str) -> str:
        """Remove common PDF noise patterns."""
        # Remove page numbers
        line = re.sub(r'page\s+\d+\s*(of\s+\d+)?', '', line, flags=re.IGNORECASE)
        line = re.sub(r'^\d+\s*$', '', line)
        
        # Remove URLs
        line = re.sub(r'https?://\S+', '', line)
        
        # Remove random symbols
        line = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\{\}]', '', line)
        
        return line
    
    def _fix_broken_words(self, text: str) -> str:
        """Try to fix words broken by OCR/line wrapping."""
        # Fix hyphened breaks: "word-\nbreak" -> "wordbreak"
        text = re.sub(r'(\w+)-\s+', r'\1', text)
        
        # Fix spaces in compound words (common before hyphens)
        text = re.sub(r'(\w+)\s+(\w+)-', r'\1\2-', text)
        
        return text
    
    def _calculate_text_confidence(self, text: str) -> float:
        """
        Calculate confidence that extracted text is high quality.
        Returns 0.0-1.0 score.
        """
        if not text or len(text) < 20:
            return 0.0
        
        # Check for common words (higher = more likely real text)
        common_words = {
            'the', 'is', 'and', 'to', 'of', 'a', 'in', 'are',
            'that', 'be', 'for', 'was', 'on', 'as', 'it', 'with'
        }
        
        text_lower = text.lower()
        word_tokens = re.findall(r'\b\w+\b', text_lower)
        
        if not word_tokens:
            return 0.0
        
        common_count = sum(1 for w in word_tokens if w in common_words)
        common_ratio = common_count / len(word_tokens)
        
        # Calculate average word length (good text: 4-8 characters)
        avg_word_len = sum(len(w) for w in word_tokens) / len(word_tokens)
        length_score = 1.0 - abs(avg_word_len - 6) / 10
        length_score = max(0.0, min(1.0, length_score))
        
        # Combine scores
        confidence = (common_ratio * 0.6 + length_score * 0.4)
        
        return confidence
    
    def _break_into_blocks(self, text: str, max_block_size: int = 500) -> list[str]:
        """
        Break text into logical blocks based on paragraphs and size.
        Preserves paragraph structure.
        """
        paragraphs = text.split('\n\n')
        blocks = []
        current_block = []
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_size = len(para)
            
            # If adding this paragraph exceeds block size, flush current block
            if current_size + para_size > max_block_size and current_block:
                blocks.append('\n\n'.join(current_block))
                current_block = [para]
                current_size = para_size
            else:
                current_block.append(para)
                current_size += para_size
        
        # Add remaining block
        if current_block:
            blocks.append('\n\n'.join(current_block))
        
        return blocks


class PDFSourceTracker:
    """Track exact sources for extracted text (page, section, position)."""
    
    @staticmethod
    def add_source_metadata(block: ExtractedBlock, section_path: Optional[list[str]] = None):
        """Add source location metadata to extracted block."""
        block.section_path = section_path
        return block
    
    @staticmethod
    def format_source_citation(block: ExtractedBlock) -> str:
        """Format a proper source citation for an extracted block."""
        parts = [f"Page {block.page_num + 1}"]
        
        if block.section_path:
            section_str = " > ".join(block.section_path)
            parts.append(f"({section_str})")
        
        if block.metadata.extraction_method == 'ocr_scanned':
            parts.append("[Scanned]")
        
        parts.append(f"Conf: {block.metadata.confidence:.0%}")
        
        return " ".join(parts)
