"""
Analysis endpoints
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException

from models.requests import AnalyzeRequest
from services.analysis_service import run_analysis_task
from utils.storage import get_document, update_document

router = APIRouter()


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

