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


def format_analysis_context(doc: dict) -> str:
    """
    Format analysis data as context for the chat prompt
    
    Args:
        doc: Document data from storage
    
    Returns:
        Formatted context string
    """
    try:
        analysis = doc.get("analysis", {})
        if not analysis:
            return None
        
        context_parts = []
        
        # Document metadata
        metadata = analysis.get("documentMetadata", {})
        context_parts.append("=== DOCUMENT ANALYSIS ===")
        context_parts.append(f"Document: {doc.get('filename', 'Unknown')}")
        
        # Key details
        key_details = analysis.get("keyDetailsDetected", {})
        if key_details:
            context_parts.append("\n--- Key Details ---")
            if key_details.get("landlord"):
                context_parts.append(f"Landlord: {key_details['landlord']}")
            if key_details.get("tenant"):
                context_parts.append(f"Tenant: {key_details['tenant']}")
            if key_details.get("propertyAddress"):
                context_parts.append(f"Property: {key_details['propertyAddress']}")
            if key_details.get("monthlyRent"):
                context_parts.append(f"Monthly Rent: {key_details['monthlyRent']}")
            if key_details.get("securityDeposit"):
                context_parts.append(f"Security Deposit: {key_details['securityDeposit']}")
            if key_details.get("leaseTerm"):
                context_parts.append(f"Lease Term: {key_details['leaseTerm']}")
        
        # Analysis summary
        summary = analysis.get("analysisSummary", {})
        if summary:
            context_parts.append("\n--- Analysis Summary ---")
            context_parts.append(f"Overall Risk Level: {summary.get('overallRisk', 'Unknown')}")
            context_parts.append(f"Issues Found: {summary.get('issuesFound', 0)}")
            context_parts.append(f"Estimated Recovery: {summary.get('estimatedRecovery', 'N/A')}")
            
            # Top issues
            top_issues = summary.get("topIssues", [])
            if top_issues:
                context_parts.append("\nTop Issues:")
                for i, issue in enumerate(top_issues[:5], 1):  # Limit to top 5
                    if isinstance(issue, dict):
                        issue_text = issue.get("title", str(issue))
                        severity = issue.get("severity", "")
                        amount = issue.get("amount", "")
                        if amount:
                            context_parts.append(f"  {i}. {issue_text} ({severity}) - {amount}")
                        else:
                            context_parts.append(f"  {i}. {issue_text} ({severity})")
                    else:
                        context_parts.append(f"  {i}. {issue}")
        
        # Highlights (key findings) - prioritize by severity and damages
        highlights = analysis.get("highlights", [])
        if highlights:
            # Sort highlights by severity (red/orange first) and damages
            sorted_highlights = sorted(
                highlights,
                key=lambda h: (
                    0 if h.get("color") == "red" else 1 if h.get("color") == "orange" else 2,
                    -(h.get("damages_estimate", 0) or 0)
                )
            )
            
            context_parts.append(f"\n--- Key Findings ({len(highlights)} total) ---")
            
            # Show top highlights with most impact
            important_highlights = []
            shown_count = 0
            max_highlights = 15  # Increased to show more context
            
            for highlight in sorted_highlights:
                if shown_count >= max_highlights:
                    break
                
                category = highlight.get("category", "Unknown")
                statute = highlight.get("statute", "")
                explanation = highlight.get("explanation", "")
                damages = highlight.get("damages_estimate", 0)
                color = highlight.get("color", "yellow")
                
                highlight_text = f"• {category}"
                if statute:
                    highlight_text += f" (M.G.L. {statute})"
                if explanation:
                    # Truncate long explanations but keep more detail
                    exp = explanation[:250] + "..." if len(explanation) > 250 else explanation
                    highlight_text += f": {exp}"
                if damages and damages > 0:
                    highlight_text += f" [Potential Recovery: ${damages:,}]"
                
                # Add severity indicator
                severity_map = {
                    "red": "CRITICAL",
                    "orange": "HIGH RISK",
                    "yellow": "MEDIUM RISK",
                    "green": "FAVORABLE"
                }
                severity = severity_map.get(color, "UNKNOWN")
                highlight_text += f" [Severity: {severity}]"
                
                important_highlights.append(highlight_text)
                shown_count += 1
            
            context_parts.extend(important_highlights)
            
            if len(highlights) > max_highlights:
                remaining = len(highlights) - max_highlights
                context_parts.append(f"\n... and {remaining} more findings")
            
            # Add summary statistics
            red_count = sum(1 for h in highlights if h.get("color") == "red")
            orange_count = sum(1 for h in highlights if h.get("color") == "orange")
            total_damages = sum(h.get("damages_estimate", 0) or 0 for h in highlights)
            
            if red_count > 0 or orange_count > 0:
                context_parts.append(f"\nSummary: {red_count} critical issues, {orange_count} high-risk issues")
            if total_damages > 0:
                context_parts.append(f"Total Potential Recovery: ${total_damages:,}")
        
        return "\n".join(context_parts)
    
    except Exception as e:
        print(f"⚠️  Error formatting analysis context: {e}")
        return None


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
    analyzer = None
    try:
        print(f"💬 Chat request received: {request.message[:100]}...")
        print(f"📄 File ID context: {request.file_id if request.file_id else 'None (general question)'}")
        
        analyzer = RAGAnalyzer()
        
        # If file_id provided, include document context and analysis data
        context_text = None
        analysis_context = None
        if request.file_id:
            try:
                doc = get_document(request.file_id)
                if doc.get("status") == "completed":
                    filename = doc.get("filename", "Unknown")
                    context_text = f"In the context of the analyzed lease '{filename}'"
                    
                    # Format analysis data as context
                    analysis_context = format_analysis_context(doc)
                    if analysis_context:
                        print(f"✅ Document context added: {filename}")
                        print(f"📊 Analysis context includes {len(doc.get('analysis', {}).get('highlights', []))} highlights")
                    else:
                        print(f"⚠️  Analysis data found but could not be formatted for {filename}")
                else:
                    print(f"⚠️  Document {request.file_id} status is '{doc.get('status')}', analysis not available")
            except Exception as e:
                print(f"⚠️  Could not load document context: {e}")
                import traceback
                traceback.print_exc()
                # Continue without context if document not found
        
        # Search for relevant laws
        search_query = request.message
        if context_text:
            search_query = f"{context_text}: {request.message}"
        
        print(f"🔍 Searching for relevant laws with query: {search_query[:100]}...")
        relevant_laws = analyzer.search_relevant_laws(search_query, top_k=5)
        print(f"✅ Found {len(relevant_laws)} relevant law sections")
        
        # Generate answer using the analyzer
        # Include both document context and analysis data
        full_context = context_text
        if analysis_context:
            if full_context:
                full_context = f"{full_context}\n\n{analysis_context}"
            else:
                full_context = analysis_context
        
        print(f"🤖 Calling Gemini API to generate response...")
        answer = analyzer.generate_chat_response(request.message, relevant_laws, full_context)
        
        if not answer or len(answer.strip()) == 0:
            answer = "I apologize, but I wasn't able to generate a response. Please try rephrasing your question."
        
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
        
        print(f"✅ Chat response generated successfully ({len(answer)} characters)")
        
        return {
            "answer": answer,
            "sources": sources,
            "context": context_text if context_text else None,
            "has_analysis_context": analysis_context is not None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Chat error: {e}")
        import traceback
        traceback.print_exc()
        if analyzer:
            try:
                analyzer.close()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

