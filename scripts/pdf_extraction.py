"""
PDF text extraction module
"""
import PyPDF2


class PDFExtractor:
    """Extract text from PDF files"""
    
    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """
        Extract text from a PDF file
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        print(f"📄 Extracting text from: {pdf_path}")
        
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            print(f"   Found {total_pages} pages")
            
            for page_num, page in enumerate(pdf_reader.pages, 1):
                print(f"   Processing page {page_num}/{total_pages}...", end='\r')
                text += page.extract_text() + "\n\n"
        
        print(f"   ✓ Extracted {len(text)} characters")
        return text.strip()

