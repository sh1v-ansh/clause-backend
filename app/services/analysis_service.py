"""
Document analysis service
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


def run_analysis_task(file_id: str, file_path: str):
    """Background task to analyze lease document"""
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
            "message": "Loading redacted text..."
        })
        
        # Use redacted text if available, otherwise extract from PDF
        if doc_metadata.get("redacted_text_path"):
            redacted_path = Path(doc_metadata["redacted_text_path"])
            if redacted_path.exists():
                with open(redacted_path, 'r', encoding='utf-8') as f:
                    lease_text = f.read()
                print(f"✅ Using PII-redacted text for analysis")
            else:
                # Fallback to original
                lease_text = extractor.extract_text(file_path)
                print(f"⚠️  Redacted text not found, using original")
        else:
            # Extract text from original PDF
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
        
        # Analyze each chunk
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
        
        # Consolidate analysis
        final_report = analyzer.consolidate_analysis(chunk_analyses, lease_text)
        
        # Add document metadata
        final_report['document_info'] = {
            'total_characters': len(lease_text),
            'total_chunks': len(lease_chunks),
            'analysis_date': datetime.now().isoformat()
        }
        
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
        
    except Exception as e:
        # Handle errors
        update_document(file_id, {
            "status": "failed",
            "progress": 0,
            "message": f"Analysis failed: {str(e)}",
            "error": str(e)
        })
        raise

