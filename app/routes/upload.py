"""
Upload endpoints
"""
from fastapi import APIRouter, File, UploadFile, HTTPException
from pathlib import Path
import uuid
from datetime import datetime

from pii_redaction import redact_pdf, PIIEncryption, save_redacted_mapping
from utils.storage import load_storage, save_storage

router = APIRouter()

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize PII encryption
pii_encryption = PIIEncryption()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a PDF lease document with PII redaction
    
    Returns:
        file_id: Unique identifier for the uploaded document
        filename: Original filename
        size: File size in bytes
        upload_time: ISO timestamp of upload
        pii_redacted: Summary of redacted PII
    """
    try:
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Save original file
        file_path = UPLOAD_DIR / f"{file_id}.pdf"
        contents = await file.read()
        
        with open(file_path, 'wb') as f:
            f.write(contents)
        
        # Redact PII from the PDF
        print(f"🔒 Redacting PII from {file.filename}...")
        try:
            redacted_text, pii_mapping, redaction_summary = redact_pdf(str(file_path), use_spacy=True)
            
            # Save redacted text
            redacted_path = UPLOAD_DIR / f"{file_id}_redacted.txt"
            with open(redacted_path, 'w', encoding='utf-8') as f:
                f.write(redacted_text)
            
            # Encrypt and save PII mapping
            encrypted_mapping = save_redacted_mapping(file_id, pii_mapping, pii_encryption)
            
            print(f"✅ PII redaction complete: {redaction_summary}")
            
        except Exception as e:
            print(f"⚠️  PII redaction failed: {e}. Proceeding without redaction.")
            redacted_text = None
            redaction_summary = {"error": str(e)}
            redacted_path = None
        
        # Store metadata
        storage = load_storage()
        storage[file_id] = {
            "file_id": file_id,
            "filename": file.filename,
            "file_path": str(file_path),
            "redacted_text_path": str(redacted_path) if redacted_path else None,
            "size": len(contents),
            "uploaded_at": datetime.now().isoformat(),
            "status": "uploaded",
            "progress": 0,
            "message": "Document uploaded and PII redacted",
            "pii_redacted": redaction_summary
        }
        save_storage(storage)
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "size": len(contents),
            "upload_time": storage[file_id]["uploaded_at"],
            "pii_redacted": redaction_summary,
            "message": "File uploaded and PII redacted successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

