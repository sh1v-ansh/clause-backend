"""
Document storage utilities
"""
import json
from pathlib import Path
from fastapi import HTTPException


STORAGE_FILE = Path("data/documents.json")
STORAGE_FILE.parent.mkdir(exist_ok=True)


def load_storage():
    """Load document storage from JSON file"""
    if STORAGE_FILE.exists():
        with open(STORAGE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_storage(storage):
    """Save document storage to JSON file"""
    with open(STORAGE_FILE, 'w') as f:
        json.dump(storage, f, indent=2)


def get_document(file_id: str):
    """Get document metadata from storage"""
    storage = load_storage()
    if file_id not in storage:
        raise HTTPException(status_code=404, detail="Document not found")
    return storage[file_id]


def update_document(file_id: str, updates: dict):
    """Update document metadata in storage"""
    storage = load_storage()
    if file_id not in storage:
        raise HTTPException(status_code=404, detail="Document not found")
    storage[file_id].update(updates)
    save_storage(storage)


def delete_document_from_storage(file_id: str):
    """Delete document from storage"""
    storage = load_storage()
    if file_id not in storage:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = storage[file_id]
    del storage[file_id]
    save_storage(storage)
    return doc

