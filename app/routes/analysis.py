"""
Analysis endpoints
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict

from models.requests import AnalyzeRequest
from services.analysis_service import run_analysis_task, run_metadata_extraction, run_full_analysis
from utils.storage import get_document, update_document

router = APIRouter()


class MetadataConfirmRequest(BaseModel):
    """Request to confirm/update metadata and start full analysis"""
    file_id: str
    metadata: Dict


@router.post("/analyze")
async def analyze_document(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Analyze a lease document for violations and risks
    
    Args:
        file_id: ID of uploaded document
    
    Returns:
        file_id: Document identifier
        status: "processing" 
        message: Status message
    """
    try:
        # Get document
        doc = get_document(request.file_id)
        
        # Check if already analyzed
        if doc.get("status") == "completed":
            return {
                "file_id": request.file_id,
                "status": "completed",
                "message": "Document already analyzed. Use GET /document/{file_id} to retrieve results."
            }
        
        # Check if currently processing
        if doc.get("status") == "processing":
            return {
                "file_id": request.file_id,
                "status": "processing",
                "progress": doc.get("progress", 0),
                "message": doc.get("message", "Analysis in progress...")
            }
        
        # Start background analysis
        background_tasks.add_task(run_analysis_task, request.file_id, doc["file_path"])
        
        # Update status
        update_document(request.file_id, {
            "status": "processing",
            "progress": 5,
            "message": "Analysis started..."
        })
        
        return {
            "file_id": request.file_id,
            "status": "processing",
            "message": "Analysis started. Use GET /status/{file_id} to check progress."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/status/{file_id}")
async def get_status(file_id: str):
    """
    Get analysis status and progress
    
    Returns:
        status: "uploaded", "processing", "completed", "failed"
        progress: 0-100
        message: Current status message
    """
    try:
        doc = get_document(file_id)
        
        return {
            "file_id": file_id,
            "status": doc.get("status", "unknown"),
            "progress": doc.get("progress", 0),
            "message": doc.get("message", ""),
            "filename": doc.get("filename", "")
        }
        
    except HTTPException:
        raise


@router.post("/extract-metadata")
async def extract_metadata(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Stage 1: Extract document metadata only
    
    Args:
        file_id: ID of uploaded document
    
    Returns:
        file_id: Document identifier
        status: "extracting_metadata"
        message: Status message
    """
    try:
        # Get document
        doc = get_document(request.file_id)
        
        # Check if metadata already extracted
        if doc.get("status") == "metadata_extracted" and doc.get("extracted_metadata"):
            return {
                "file_id": request.file_id,
                "status": "metadata_extracted",
                "metadata": doc.get("extracted_metadata"),
                "message": "Metadata already extracted"
            }
        
        # Start background metadata extraction
        background_tasks.add_task(run_metadata_extraction, request.file_id, doc["file_path"])
        
        return {
            "file_id": request.file_id,
            "status": "extracting_metadata",
            "message": "Metadata extraction started. Poll /status/{file_id} to check progress."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {str(e)}")


@router.get("/metadata/{file_id}")
async def get_metadata(file_id: str):
    """
    Get extracted metadata for a document
    
    Returns:
        file_id: Document ID
        status: Extraction status
        metadata: Extracted metadata (if available)
    """
    try:
        doc = get_document(file_id)
        
        return {
            "file_id": file_id,
            "status": doc.get("status", "unknown"),
            "metadata": doc.get("extracted_metadata"),
            "message": doc.get("message", "")
        }
        
    except HTTPException:
        raise


@router.post("/confirm-metadata")
async def confirm_metadata(request: MetadataConfirmRequest, background_tasks: BackgroundTasks):
    """
    Stage 2: Confirm/update metadata and start full analysis
    
    Args:
        file_id: ID of document
        metadata: User-confirmed or updated metadata
    
    Returns:
        file_id: Document identifier
        status: "processing"
        message: Status message
    """
    try:
        # Get document
        doc = get_document(request.file_id)
        
        # Update with user-confirmed metadata
        update_document(request.file_id, {
            "extracted_metadata": request.metadata
        })
        
        # Start full analysis in background
        background_tasks.add_task(run_full_analysis, request.file_id, doc["file_path"], request.metadata)
        
        return {
            "file_id": request.file_id,
            "status": "processing",
            "message": "Full analysis started with confirmed metadata. Poll /status/{file_id} to check progress."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

