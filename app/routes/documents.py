"""
Document management endpoints
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path

from utils.storage import load_storage, get_document, delete_document_from_storage

router = APIRouter()


@router.get("/document/{file_id}")
async def get_document_analysis(file_id: str):
    """
    Get document metadata and analysis results
    
    Returns:
        document_info: Metadata about the document
        analysis: Full analysis results including violations, risks, and recommendations
    """
    try:
        doc = get_document(file_id)
        
        if doc.get("status") != "completed":
            return {
                "file_id": file_id,
                "status": doc.get("status", "unknown"),
                "message": "Analysis not complete yet. Check /status/{file_id}",
                "progress": doc.get("progress", 0)
            }
        
        return {
            "file_id": file_id,
            "filename": doc["filename"],
            "uploaded_at": doc["uploaded_at"],
            "analyzed_at": doc.get("analyzed_at"),
            "status": "completed",
            "analysis": doc.get("analysis", {})
        }
        
    except HTTPException:
        raise


@router.get("/documents")
async def list_documents():
    """
    List all uploaded documents
    
    Returns:
        List of documents with metadata
    """
    try:
        storage = load_storage()
        
        documents = []
        for file_id, doc in storage.items():
            documents.append({
                "file_id": file_id,
                "filename": doc.get("filename", "Unknown"),
                "uploaded_at": doc.get("uploaded_at"),
                "status": doc.get("status", "unknown"),
                "size": doc.get("size", 0)
            })
        
        # Sort by upload time (newest first)
        documents.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
        
        return {
            "total": len(documents),
            "documents": documents
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.delete("/document/{file_id}")
async def delete_document(file_id: str):
    """
    Delete a document and its analysis
    
    Returns:
        Success message
    """
    try:
        doc = delete_document_from_storage(file_id)
        
        # Delete file
        file_path = Path(doc["file_path"])
        if file_path.exists():
            file_path.unlink()
        
        # Delete redacted text if exists
        if doc.get("redacted_text_path"):
            redacted_path = Path(doc["redacted_text_path"])
            if redacted_path.exists():
                redacted_path.unlink()
        
        return {
            "message": "Document deleted successfully",
            "file_id": file_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

