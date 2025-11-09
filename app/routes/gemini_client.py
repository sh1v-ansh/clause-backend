"""
Gemini client for demand letter generation
"""
import google.generativeai as genai
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys

# Add scripts directory to path - get the root of clause_backend
current_dir = os.path.dirname(os.path.abspath(__file__))  # routes/
app_dir = os.path.dirname(current_dir)  # app/
backend_root = os.path.dirname(app_dir)  # clause_backend/
scripts_dir = os.path.join(backend_root, 'scripts')
sys.path.insert(0, scripts_dir)

try:
    from demand_letter_helpers import (
        build_user_prompt,
        validate_latex,
        clean_latex_output
    )
except ImportError as e:
    print(f"[ERROR] Failed to import demand_letter_helpers: {e}")
    print(f"   Current dir: {current_dir}")
    print(f"   Scripts dir: {scripts_dir}")
    print(f"   Scripts dir exists: {os.path.exists(scripts_dir)}")
    raise

# Load environment variables - try multiple paths
current_file = os.path.abspath(__file__)  # routes/gemini_client.py
app_dir = os.path.dirname(os.path.dirname(current_file))  # app/
backend_root = os.path.dirname(app_dir)  # clause_backend/
env_path = os.path.join(backend_root, '.env')

# Try loading from backend root first, then fallback to current directory
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"[OK] Loaded .env from: {env_path}")
else:
    load_dotenv()  # Try current directory
    print(f"[WARN] .env not found at {env_path}, trying current directory")

# System instruction for Gemini - optimized for token efficiency
SYSTEM_INSTRUCTION = """Generate professional demand letters in plain text for Massachusetts tenant law violations.

Requirements:
- Plain text only (NO markdown, NO LaTeX)
- Format: sender address, date, recipient address, RE line, salutation, body, closing, signature
- Include: violations with M.G.L. citations, damages breakdown, total amount, deadline, consequences
- Use placeholders: [YOUR NAME], [YOUR ADDRESS], [LANDLORD NAME], [LANDLORD ADDRESS], [DATE]
- Professional, firm tone
- Massachusetts law only
- Ready to copy/paste"""


def initialize_gemini():
    """Initialize Gemini client with API key from environment"""
    api_key = os.environ.get('GEMINI_API_KEY')
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=api_key)
    
    # Use a model that exists - try gemini-2.0-flash-exp (same as rag_analyzer) or fallback to gemini-flash-latest
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp')
    
    # Remove 'models/' prefix if present (some APIs include it, others don't)
    if model_name.startswith('models/'):
        model_name = model_name.replace('models/', '')
    
    print(f"   Using Gemini model: {model_name}")
    
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_INSTRUCTION
    )


def generate_demand_letter(request_data):
    """
    Generate demand letter using Gemini API
    
    Args:
        request_data: Dictionary containing prompt, analysis_json, sender, recipient, preferences
    
    Returns:
        Dictionary with success status, latex_source, and metadata
    """
    try:
        # Initialize model
        model = initialize_gemini()
        
        # Build the prompt - ensure we have all required data
        prompt = request_data.get('prompt') or ''
        analysis_json = request_data.get('analysis_json', {})
        sender = request_data.get('sender', {})
        recipient = request_data.get('recipient', {})
        preferences = request_data.get('preferences', {})
        
        print(f"   Building prompt with:")
        print(f"     - Prompt: {prompt[:50] if prompt else 'None'}...")
        print(f"     - Sender: {sender.get('name', 'N/A')}")
        print(f"     - Recipient: {recipient.get('name', 'N/A')}")
        print(f"     - Highlights: {len(analysis_json.get('highlights', []))}")
        
        user_prompt = build_user_prompt(
            prompt,
            analysis_json,
            sender,
            recipient,
            preferences
        )
        
        # Optimize prompt length to reduce token usage for free tier
        # Limit to top 3 highlights with highest damages to minimize tokens
        highlights = analysis_json.get('highlights', [])
        if len(highlights) > 3:
            # Sort by damages_estimate and take top 3
            sorted_highlights = sorted(
                highlights, 
                key=lambda h: h.get('damages_estimate', 0) or 0, 
                reverse=True
            )[:3]
            analysis_json_optimized = analysis_json.copy()
            analysis_json_optimized['highlights'] = sorted_highlights
            # Update issues_found in summary to reflect reduction
            if 'analysisSummary' in analysis_json_optimized:
                analysis_json_optimized['analysisSummary'] = analysis_json_optimized['analysisSummary'].copy()
                analysis_json_optimized['analysisSummary']['issuesFound'] = 3
            # Rebuild prompt with optimized data
            user_prompt = build_user_prompt(
                prompt,
                analysis_json_optimized,
                sender,
                recipient,
                preferences
            )
            print(f"   [OPTIMIZED] Reduced highlights from {len(highlights)} to 3 (top damages) to save tokens")
        
        print("Generating demand letter with Gemini...")
        print(f"   Prompt length: {len(user_prompt)} characters (~{len(user_prompt) // 4} tokens)")
        model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp')
        if model_name.startswith('models/'):
            model_name = model_name.replace('models/', '')
        print(f"   Model: {model_name}")
        
        # Generate content with retry logic
        # Optimized for free tier - reduced tokens and retries
        max_retries = 1  # Single attempt to avoid hitting rate limits
        for attempt in range(max_retries):
            try:
                response = model.generate_content(
                    user_prompt,
                    generation_config={
                        'temperature': 0.3,  # Lower temperature for consistent, formal output
                        'top_p': 0.95,
                        'top_k': 40,
                        'max_output_tokens': 1500,  # Reduced further for free tier (was 4096)
                    }
                )
                print("[OK] Gemini API call successful")
                break
            except Exception as e:
                error_msg = str(e)
                print(f"[ERROR] Gemini API error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                
                # Check for rate limit errors
                if "429" in error_msg or "quota" in error_msg.lower() or "limit" in error_msg.lower():
                    raise Exception(f"Rate limit exceeded: {error_msg}. Please wait before trying again or check your API quota.")
                
                if attempt == max_retries - 1:
                    raise
                import time
                time.sleep(2)  # Wait 2 seconds before retry
        
        # Extract text from response
        latex_source = None
        try:
            # Try the standard response.text attribute first
            if hasattr(response, 'text') and response.text:
                latex_source = response.text.strip()
                print(f"   Extracted text: {len(latex_source)} characters")
        except AttributeError:
            pass
        
        # If that didn't work, try alternative response formats
        if not latex_source:
            try:
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content'):
                        if hasattr(candidate.content, 'parts'):
                            latex_source = candidate.content.parts[0].text.strip()
                            print(f"   Extracted text: {len(latex_source)} characters")
                        elif hasattr(candidate.content, 'text'):
                            latex_source = candidate.content.text.strip()
                            print(f"   Extracted text: {len(latex_source)} characters")
            except Exception as e:
                print(f"   Warning: Could not extract via candidates: {e}")
        
        # If still no text, try to get raw response
        if not latex_source:
            try:
                # Last resort: try to stringify the response
                latex_source = str(response).strip()
                print(f"   Extracted text: {len(latex_source)} characters")
            except Exception as e:
                raise Exception(f"Could not extract text from Gemini response: {e}. Response type: {type(response)}")
        
        if not latex_source or len(latex_source) < 50:
            raise Exception(f"Generated text is too short or empty: {len(latex_source) if latex_source else 0} characters")
        
        # Clean up any markdown formatting
        letter_text = clean_latex_output(latex_source)
        
        # Validate content (lenient - just check it has substantial content)
        if not validate_latex(letter_text):
            # Still return it even if validation fails - let user decide
            print(f"[WARN] Validation warning: Generated content may be incomplete, but returning anyway")
            # Don't fail - return the content
        
        # Calculate deadline date
        deadline_days = request_data.get('preferences', {}).get('deadline_days', 30)
        deadline_date = datetime.now() + timedelta(days=deadline_days)
        
        # Calculate total damages
        highlights = request_data.get('analysis_json', {}).get('highlights', [])
        total_damages = sum(
            (h.get('damages_estimate', 0) or 0) 
            for h in highlights
        )
        
        # Return successful response - use 'letter_text' instead of 'latex_source' for clarity
        return {
            'success': True,
            'latex_source': letter_text,  # Keep field name for compatibility
            'letter_text': letter_text,   # Also provide as letter_text
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_damages': total_damages,
                'issues_count': len(highlights),
                'deadline_date': deadline_date.strftime('%Y-%m-%d'),
                'model_used': os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp').replace('models/', '')
            }
        }
        
    except Exception as e:
        print(f"Error generating demand letter: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'error_code': 'GENERATION_FAILED'
        }

