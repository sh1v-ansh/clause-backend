"""
PDF Coordinate Extractor - Locates text positions in PDF for highlighting
"""
import pdfplumber
from typing import List, Dict, Optional, Tuple
import re


class PDFCoordinateExtractor:
    """Extract text coordinates from PDF files for highlighting"""
    
    def __init__(self, pdf_path: str):
        """
        Initialize with PDF path
        
        Args:
            pdf_path: Path to PDF file
        """
        self.pdf_path = pdf_path
        self.pdf = pdfplumber.open(pdf_path)
        print(f"📍 Loaded PDF for coordinate extraction: {pdf_path}")
    
    def find_text_coordinates(self, search_text: str, page_number: Optional[int] = None) -> Optional[Dict]:
        """
        Find coordinates of text in PDF
        
        Args:
            search_text: Text to search for
            page_number: Specific page to search (1-indexed), or None to search all pages
            
        Returns:
            Dictionary with position data or None if not found
        """
        # Clean the search text
        clean_search = self._clean_text(search_text)
        
        # Determine which pages to search
        pages_to_search = [page_number] if page_number else range(1, len(self.pdf.pages) + 1)
        
        # Try multiple search strategies with different snippet lengths
        snippet_lengths = [200, 150, 100, 75, 50]
        
        for page_num in pages_to_search:
            page = self.pdf.pages[page_num - 1]  # Convert to 0-indexed
            page_text = page.extract_text()
            
            if not page_text:
                continue
            
            clean_page_text = self._clean_text(page_text)
            
            # Try different snippet lengths to find a match
            for snippet_len in snippet_lengths:
                search_snippet = clean_search[:snippet_len]
                
                if len(search_snippet) < 20:  # Too short, skip
                    continue
                
                if search_snippet in clean_page_text:
                    # Found the text, now get coordinates
                    coords = self._extract_coordinates(page, search_text, page_num)
                    if coords:
                        return coords
                    break  # If extraction failed, try next page
        
        # If exact match not found, return estimated coordinates
        # Get page for dimensions
        fallback_page_num = page_number or 1
        if fallback_page_num <= len(self.pdf.pages):
            fallback_page = self.pdf.pages[fallback_page_num - 1]
            return self._create_default_coordinates(fallback_page_num, fallback_page.height, fallback_page.width)
        return self._create_default_coordinates(fallback_page_num)
    
    def _extract_coordinates(self, page, text: str, page_num: int) -> Optional[Dict]:
        """
        Extract actual coordinates from page
        
        Args:
            page: pdfplumber page object
            text: Text to locate
            page_num: Page number (1-indexed)
            
        Returns:
            Position dictionary with bounding boxes (in PDF.js/react-pdf-highlighter format)
        """
        try:
            # Get page dimensions for coordinate transformation
            page_height = page.height
            page_width = page.width
            
            # Get all words with their bounding boxes
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            
            if not words:
                return self._create_default_coordinates(page_num, page_height, page_width)
            
            # Split search text into words
            search_words = text.split()[:30]  # Use first 30 words for better matching
            clean_search_words = [self._clean_text(sw) for sw in search_words if sw.strip()]
            
            # Find matching sequence using sliding window
            word_positions = []
            best_match_positions = []
            current_match = []
            
            for i, word in enumerate(words):
                word_text = self._clean_text(word['text'])
                
                # Check if this word matches any of our search words
                for search_word in clean_search_words:
                    if search_word and word_text and (search_word in word_text or word_text in search_word):
                        current_match.append(word)
                        break
                else:
                    # No match, check if we have a good sequence
                    if len(current_match) > len(best_match_positions):
                        best_match_positions = current_match
                    current_match = []
                
                # Stop if we have enough words
                if len(current_match) >= min(len(clean_search_words), 15):
                    best_match_positions = current_match
                    break
            
            # Final check
            if len(current_match) > len(best_match_positions):
                best_match_positions = current_match
            
            word_positions = best_match_positions if best_match_positions else []
            
            if not word_positions:
                return self._create_default_coordinates(page_num, page_height, page_width)
            
            # Calculate bounding box from word positions (pdfplumber coordinates)
            x0 = min(w['x0'] for w in word_positions)
            y0_pdf = min(w['top'] for w in word_positions)
            x1 = max(w['x1'] for w in word_positions)
            y1_pdf = max(w['bottom'] for w in word_positions)
            
            # Transform to PDF.js/react-pdf-highlighter coordinate system
            # In PDF.js, Y-axis origin is at BOTTOM-LEFT (increases upward)
            # In pdfplumber, Y-axis origin is at TOP-LEFT (increases downward)
            # Transformation: pdf_js_y = page_height - pdfplumber_y
            y0 = round(page_height - y1_pdf, 2)  # Bottom edge in PDF.js
            y1 = round(page_height - y0_pdf, 2)  # Top edge in PDF.js
            
            # Create rects for multi-line text (group by approximate y position)
            rects = []
            current_line = []
            last_y = None
            
            for word in word_positions:
                if last_y is None or abs(word['top'] - last_y) < 5:  # Same line
                    current_line.append(word)
                else:
                    if current_line:
                        rects.append(self._create_rect_from_words(current_line, page_num, page_height))
                    current_line = [word]
                last_y = word['top']
            
            if current_line:
                rects.append(self._create_rect_from_words(current_line, page_num, page_height))
            
            return {
                "boundingRect": {
                    "x1": round(x0, 2),
                    "y1": y0,
                    "x2": round(x1, 2),
                    "y2": y1,
                    "width": round(x1 - x0, 2),
                    "height": round(y1 - y0, 2),
                    "pageNumber": page_num
                },
                "rects": rects if rects else [
                    {
                        "x1": round(x0, 2),
                        "y1": y0,
                        "x2": round(x1, 2),
                        "y2": y1,
                        "width": round(x1 - x0, 2),
                        "height": round(y1 - y0, 2),
                        "pageNumber": page_num
                    }
                ],
                "pageHeight": page_height,
                "pageWidth": page_width
            }
            
        except Exception as e:
            print(f"⚠️  Error extracting coordinates: {e}")
            # Try to get page dimensions for default coordinates
            try:
                return self._create_default_coordinates(page_num, page.height, page.width)
            except:
                return self._create_default_coordinates(page_num)
    
    def _create_rect_from_words(self, words: List[Dict], page_num: int, page_height: float) -> Dict:
        """
        Create a rectangle from a list of words
        
        Args:
            words: List of word dictionaries with positions
            page_num: Page number (1-indexed)
            page_height: Height of the page for coordinate transformation
            
        Returns:
            Rectangle in PDF.js/react-pdf-highlighter coordinate system
        """
        x0 = min(w['x0'] for w in words)
        x1 = max(w['x1'] for w in words)
        y0_pdf = min(w['top'] for w in words)
        y1_pdf = max(w['bottom'] for w in words)
        
        # Transform to PDF.js coordinate system
        y0 = round(page_height - y1_pdf, 2)
        y1 = round(page_height - y0_pdf, 2)
        
        return {
            "x1": round(x0, 2),
            "y1": y0,
            "x2": round(x1, 2),
            "y2": y1,
            "width": round(x1 - x0, 2),
            "height": round(y1 - y0, 2),
            "pageNumber": page_num
        }
    
    def _create_default_coordinates(self, page_num: int, page_height: float = None, page_width: float = None) -> Dict:
        """
        Create default coordinates when text cannot be found
        
        Args:
            page_num: Page number
            page_height: Height of the page (optional)
            page_width: Width of the page (optional)
            
        Returns:
            Default position dictionary in PDF.js/react-pdf-highlighter format
        """
        # Default values in pdfplumber coordinate system
        # (approximate middle of a standard US Letter page)
        x1_default = 72
        x2_default = 540
        y_top_pdf = 200  # From top in pdfplumber
        y_bottom_pdf = 250
        
        # Transform to PDF.js coordinates if page height is available
        if page_height:
            # Convert from pdfplumber (top-origin) to PDF.js (bottom-origin)
            y1 = round(page_height - y_bottom_pdf, 2)
            y2 = round(page_height - y_top_pdf, 2)
        else:
            # Fallback: assume standard letter size (792 points)
            page_height = 792
            page_width = 612
            y1 = round(page_height - y_bottom_pdf, 2)
            y2 = round(page_height - y_top_pdf, 2)
        
        if not page_width:
            page_width = 612
        
        return {
            "boundingRect": {
                "x1": x1_default,
                "y1": y1,
                "x2": x2_default,
                "y2": y2,
                "width": x2_default - x1_default,
                "height": y2 - y1,
                "pageNumber": page_num
            },
            "rects": [
                {
                    "x1": x1_default,
                    "y1": y1,
                    "x2": x2_default,
                    "y2": y2,
                    "width": x2_default - x1_default,
                    "height": y2 - y1,
                    "pageNumber": page_num
                }
            ],
            "pageHeight": page_height,
            "pageWidth": page_width
        }
    
    def _clean_text(self, text: str) -> str:
        """Clean text for comparison"""
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text)
        text = text.strip().lower()
        return text
    
    def close(self):
        """Close the PDF file"""
        self.pdf.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

