"""
Document analysis service - Direct analysis without metadata extraction
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
from pdf_extraction import PDFExtractor
from document_chunker import DocumentChunker
from rag_analyzer import RAGAnalyzer

from utils.storage import get_document, update_document


def run_metadata_extraction(file_id: str, file_path: str):
    """
    Stage 1: Extract document metadata
    
    Args:
        file_id: Document ID
        file_path: Path to PDF file
        
    Returns:
        Extracted metadata dictionary
    """
    try:
        print("🔍 Stage 1: Metadata Extraction")
        
        # Update status
        update_document(file_id, {
            "status": "extracting_metadata",
            "progress": 10,
            "message": "Extracting document metadata..."
        })
        
        # Initialize components
        extractor = PDFExtractor()
        analyzer = RAGAnalyzer()
        
        # Get document metadata
        doc_metadata = get_document(file_id)
        
        # Extract text
        if doc_metadata.get("redacted_text_path"):
            redacted_path = Path(doc_metadata["redacted_text_path"])
            if redacted_path.exists():
                with open(redacted_path, 'r', encoding='utf-8') as f:
                    lease_text = f.read()
                print(f"✅ Using PII-redacted text")
            else:
                lease_text = extractor.extract_text(file_path)
                print(f"⚠️  Redacted text not found, using original")
        else:
            lease_text = extractor.extract_text(file_path)
            print(f"⚠️  No PII redaction performed, using original text")
        
        # Extract metadata using Gemini
        metadata = analyzer.extract_metadata(lease_text, file_path)
        
        # Close analyzer
        analyzer.close()
        
        # Update document with extracted metadata
        update_document(file_id, {
            "status": "metadata_extracted",
            "progress": 30,
            "message": "Metadata extracted. Ready for full analysis.",
            "extracted_metadata": metadata
        })
        
        return metadata
        
    except Exception as e:
        update_document(file_id, {
            "status": "metadata_extraction_failed",
            "progress": 0,
            "message": f"Metadata extraction failed: {str(e)}",
            "error": str(e)
        })
        raise


def run_full_analysis(file_id: str, file_path: str, user_metadata: dict = None):
    """
    Stage 2: Run full analysis with user-confirmed metadata
    
    Args:
        file_id: Document ID
        file_path: Path to PDF file
        user_metadata: User-confirmed or supplemented metadata
    """
    try:
        print("🔬 Stage 2: Full Analysis")
        
        # Update status to processing
        update_document(file_id, {
            "status": "processing",
            "progress": 35,
            "message": "Initializing full analysis..."
        })
        
        # Initialize components
        extractor = PDFExtractor()
        chunker = DocumentChunker()
        analyzer = RAGAnalyzer()
        
        # Get document metadata
        doc_metadata = get_document(file_id)
        
        # Use user metadata if provided, otherwise use extracted metadata
        if user_metadata:
            metadata = user_metadata
        else:
            metadata = doc_metadata.get("extracted_metadata", {})
        
        update_document(file_id, {
            "progress": 40,
            "message": "Loading document text..."
        })
        
        # Use redacted text if available
        if doc_metadata.get("redacted_text_path"):
            redacted_path = Path(doc_metadata["redacted_text_path"])
            if redacted_path.exists():
                with open(redacted_path, 'r', encoding='utf-8') as f:
                    lease_text = f.read()
                print(f"✅ Using PII-redacted text for analysis")
            else:
                lease_text = extractor.extract_text(file_path)
                print(f"⚠️  Redacted text not found, using original")
        else:
            lease_text = extractor.extract_text(file_path)
            print(f"⚠️  No PII redaction performed, using original text")
        
        update_document(file_id, {
            "progress": 45,
            "message": "Chunking document..."
        })
        
        # Chunk document
        lease_chunks = chunker.chunk_document(lease_text, max_tokens=4000)
        
        update_document(file_id, {
            "progress": 50,
            "message": f"Analyzing {len(lease_chunks)} chunks against MA laws..."
        })
        
        # Analyze each chunk
        chunk_analyses = []
        for i, chunk in enumerate(lease_chunks):
            progress = 50 + int((i / len(lease_chunks)) * 35)
            update_document(file_id, {
                "progress": progress,
                "message": f"Analyzing chunk {i+1}/{len(lease_chunks)}..."
            })
            
            relevant_laws = analyzer.search_relevant_laws(chunk['text'], top_k=8)
            analysis = analyzer.analyze_chunk(chunk, relevant_laws)
            chunk_analyses.append(analysis)
        
        update_document(file_id, {
            "progress": 85,
            "message": "Consolidating findings and extracting coordinates..."
        })
        
        # Get PII summary
        pii_summary = doc_metadata.get("pii_redacted", {})
        
        # Consolidate analysis with complete structure
        final_report = analyzer.consolidate_analysis(
            chunk_analyses, 
            lease_text,
            metadata,
            pii_summary,
            file_id,
            file_path
        )
        
        # Close analyzer
        analyzer.close()
        
        # Update with final results
        update_document(file_id, {
            "status": "completed",
            "progress": 100,
            "message": "Analysis complete",
            "analysis": final_report,
            "analyzed_at": datetime.now().isoformat()
        })
        
        print("✅ Full analysis complete")
        
    except Exception as e:
        # Handle errors
        update_document(file_id, {
            "status": "failed",
            "progress": 0,
            "message": f"Analysis failed: {str(e)}",
            "error": str(e)
        })
        raise


def run_analysis_task(file_id: str, file_path: str):
    """
    Background task to analyze lease document
    Skips metadata extraction to save API calls - goes straight to analysis
    """
    try:
        # Update status to processing
        update_document(file_id, {
            "status": "processing",
            "progress": 10,
            "message": "Initializing analyzer..."
        })
        
        # Initialize components
        extractor = PDFExtractor()
        chunker = DocumentChunker()
        analyzer = RAGAnalyzer()
        
        # Get document metadata
        doc_metadata = get_document(file_id)
        
        update_document(file_id, {
            "progress": 20,
            "message": "Loading document text..."
        })
        
        # Use redacted text if available, otherwise extract from PDF
        if doc_metadata.get("redacted_text_path"):
            redacted_path = Path(doc_metadata["redacted_text_path"])
            if redacted_path.exists():
                with open(redacted_path, 'r', encoding='utf-8') as f:
                    lease_text = f.read()
                print(f"✅ Using PII-redacted text for analysis")
            else:
                lease_text = extractor.extract_text(file_path)
                print(f"⚠️  Redacted text not found, using original")
        else:
            lease_text = extractor.extract_text(file_path)
            print(f"⚠️  No PII redaction performed, using original text")
        
        update_document(file_id, {
            "progress": 30,
            "message": "Chunking document..."
        })
        
        # Chunk document
        lease_chunks = chunker.chunk_document(lease_text, max_tokens=4000)
        
        update_document(file_id, {
            "progress": 40,
            "message": f"Analyzing {len(lease_chunks)} chunks against MA laws..."
        })
        
        # Analyze each chunk (this is the main API call usage)
        chunk_analyses = []
        for i, chunk in enumerate(lease_chunks):
            progress = 40 + int((i / len(lease_chunks)) * 40)
            update_document(file_id, {
                "progress": progress,
                "message": f"Analyzing chunk {i+1}/{len(lease_chunks)}..."
            })
            
            relevant_laws = analyzer.search_relevant_laws(chunk['text'], top_k=8)
            analysis = analyzer.analyze_chunk(chunk, relevant_laws)
            chunk_analyses.append(analysis)
        
        update_document(file_id, {
            "progress": 85,
            "message": "Consolidating findings..."
        })
        
        # Get basic file info without calling Gemini
        import PyPDF2
        page_count = None
        file_size = None
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                page_count = len(pdf_reader.pages)
            file_size = os.path.getsize(file_path)
        except:
            pass
        
        # Create minimal metadata without Gemini API call
        minimal_metadata = {
            "fileName": doc_metadata.get("filename", "Document"),
            "documentType": "Lease Agreement",
            "uploadDate": datetime.now().strftime("%Y-%m-%d"),
            "fileSize": f"{file_size // 1024} KB" if file_size else "Unknown",
            "pageCount": page_count,
            "parties": {
                "landlord": "See document",
                "tenant": "See document", 
                "property": "See document"
            },
            "leaseDetails": {
                "leaseType": "To be determined",
                "propertyAddress": "See document",
                "leaseTerm": "See document",
                "monthlyRent": "See document",
                "securityDeposit": "See document",
                "specialClauses": []
            }
        }
        
        # Get PII summary
        pii_summary = doc_metadata.get("pii_redacted", {})
        
        # Consolidate analysis with complete structure
        final_report = analyzer.consolidate_analysis(
            chunk_analyses, 
            lease_text,
            minimal_metadata,
            pii_summary,
            file_id,
            file_path
        )
        
        # Close analyzer
        analyzer.close()
        
        # Update with final results
        update_document(file_id, {
            "status": "completed",
            "progress": 100,
            "message": "Analysis complete",
            "analysis": final_report,
            "analyzed_at": datetime.now().isoformat()
        })
        
        print("✅ Analysis complete")
        
    except Exception as e:
        # Handle errors
        update_document(file_id, {
            "status": "failed",
            "progress": 0,
            "message": f"Analysis failed: {str(e)}",
            "error": str(e)
        })
        print(f"❌ Analysis failed: {e}")
        raise
