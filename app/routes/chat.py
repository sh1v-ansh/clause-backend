"""
Chat endpoints for RAG queries
"""
from fastapi import APIRouter, HTTPException
import sys
import os

# Add scripts directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
from rag_analyzer import RAGAnalyzer

from models.requests import ChatRequest
from utils.storage import get_document

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat with RAG system about MA housing laws
    
    Args:
        message: User's question
        file_id: (Optional) Context of specific document
    
    Returns:
        answer: AI-generated response
        sources: Relevant law sections used
        context: Document context if file_id provided
    """
    try:
        analyzer = RAGAnalyzer()
        
        # If file_id provided, include document context
        context_text = None
        if request.file_id:
            try:
                doc = get_document(request.file_id)
                if doc.get("status") == "completed":
                    context_text = f"In the context of the analyzed lease '{doc['filename']}'"
            except:
                pass
        
        # Search for relevant laws
        search_query = request.message
        if context_text:
            search_query = f"{context_text}: {request.message}"
        
        relevant_laws = analyzer.search_relevant_laws(search_query, top_k=5)
        
        # Generate answer using the analyzer
        answer = analyzer.generate_chat_response(request.message, relevant_laws, context_text)
        
        analyzer.close()
        
        # Format sources
        sources = [
            {
                "chapter": law["chapter"],
                "section": law["section"],
                "relevance": f"{law['similarity']:.2f}"
            }
            for law in relevant_laws
        ]
        
        return {
            "answer": answer,
            "sources": sources,
            "context": context_text
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

