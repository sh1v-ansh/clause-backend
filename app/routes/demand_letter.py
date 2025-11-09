"""
Demand letter generation endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from .gemini_client import generate_demand_letter
import sys
import os

# Add scripts directory to path - get the root of clause_backend
current_dir = os.path.dirname(os.path.abspath(__file__))  # routes/
app_dir = os.path.dirname(current_dir)  # app/
backend_root = os.path.dirname(app_dir)  # clause_backend/
scripts_dir = os.path.join(backend_root, 'scripts')
sys.path.insert(0, scripts_dir)

try:
    from demand_letter_helpers import validate_request_data
except ImportError as e:
    print(f"[ERROR] Failed to import demand_letter_helpers: {e}")
    print(f"   Current dir: {current_dir}")
    print(f"   Scripts dir: {scripts_dir}")
    print(f"   Scripts dir exists: {os.path.exists(scripts_dir)}")
    raise

router = APIRouter()


class SenderInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class RecipientInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    contact_person: Optional[str] = None


class Preferences(BaseModel):
    deadline_days: Optional[int] = 30
    tone: Optional[str] = "firm"


class DemandLetterRequest(BaseModel):
    prompt: Optional[str] = None
    analysis_json: Dict[str, Any]
    sender: Optional[SenderInfo] = None
    recipient: Optional[RecipientInfo] = None
    preferences: Optional[Preferences] = None


@router.post("/generate")
async def generate_demand_letter_endpoint(request: DemandLetterRequest):
    """
    Generate a demand letter based on lease analysis
    
    Returns:
        success: Boolean indicating if generation succeeded
        latex_source: The generated LaTeX document
        metadata: Information about the generation
    """
    try:
        print(f"[REQUEST] Received demand letter request")
        print(f"   Analysis JSON keys: {list(request.analysis_json.keys())}")
        print(f"   Highlights count: {len(request.analysis_json.get('highlights', []))}")
        
        # Convert Pydantic models to dict - handle optional fields
        # Use dict(exclude_unset=True) to only include fields that were actually provided
        request_dict = {
            'prompt': request.prompt,
            'analysis_json': request.analysis_json,
            'sender': request.sender.dict() if request.sender else {},
            'recipient': request.recipient.dict() if request.recipient else {},
            'preferences': request.preferences.dict() if request.preferences else {}
        }
        
        # Log what we received
        print(f"   Request dict keys: {list(request_dict.keys())}")
        print(f"   Sender provided: {bool(request_dict.get('sender'))}")
        print(f"   Recipient provided: {bool(request_dict.get('recipient'))}")
        print(f"   Preferences provided: {bool(request_dict.get('preferences'))}")
        
        # Validate request data
        print("[VALIDATE] Validating request data...")
        validation_error = validate_request_data(request_dict)
        if validation_error:
            print(f"[ERROR] Validation error: {validation_error}")
            raise HTTPException(status_code=400, detail=validation_error)
        
        print(f"[OK] Validation passed")
        print(f"[INFO] Generating demand letter for document: {request.analysis_json.get('documentMetadata', {}).get('fileName', 'Unknown')}")
        print(f"[INFO] Issues found: {len(request.analysis_json.get('highlights', []))}")
        
        # Generate the demand letter
        # Note: generate_demand_letter expects the dict structure directly
        # Validation will fill in defaults if sender/recipient are missing
        print("[GENERATE] Calling generate_demand_letter...")
        result = generate_demand_letter(request_dict)
        
        print(f"[RESULT] Received result: success={result.get('success')}")
        
        if not result.get("success"):
            error_detail = result.get('error', 'Unknown error')
            error_code = result.get('error_code', 'UNKNOWN_ERROR')
            print(f"[ERROR] Generation failed: {error_detail} (code: {error_code})")
            
            # Check for rate limit errors and provide helpful message
            if "429" in error_detail or "quota" in error_detail.lower() or "limit" in error_detail.lower():
                raise HTTPException(
                    status_code=429,
                    detail=f"API rate limit exceeded. Please wait before trying again or check your Gemini API quota.",
                    headers={"X-Error-Code": "RATE_LIMIT_EXCEEDED"}
                )
            
            raise HTTPException(
                status_code=500, 
                detail=f"Generation failed: {error_detail}",
                headers={"X-Error-Code": error_code}
            )
        
        print(f"[SUCCESS] Demand letter generated successfully")
        print(f"[INFO] Letter length: {len(result.get('latex_source', ''))} characters")
        
        return {
            "success": True,
            "latex_source": result.get("latex_source", "") or result.get("letter_text", ""),
            "letter_text": result.get("letter_text", "") or result.get("latex_source", ""),
            "metadata": result.get("metadata", {})
        }
        
    except HTTPException as he:
        print(f"[ERROR] HTTPException raised: {he.detail}")
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Error in demand letter endpoint: {error_msg}")
        import traceback
        traceback.print_exc()
        
        # Check for rate limit errors
        if "429" in error_msg or "quota" in error_msg.lower() or "limit" in error_msg.lower():
            raise HTTPException(
                status_code=429,
                detail=f"API rate limit exceeded: {error_msg}. Please wait before trying again or check your Gemini API quota.",
            )
        
        raise HTTPException(
            status_code=500, 
            detail=f"Demand letter generation failed: {error_msg}"
        )

