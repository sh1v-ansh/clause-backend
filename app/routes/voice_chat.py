"""
Voice chat endpoint for speech-to-speech communication
Uses Gemini for STT and chat, ElevenLabs for TTS
Supports English and Chinese
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import os
import sys
import io
import tempfile
import urllib.parse
from typing import Optional, Tuple
import time

# Add scripts directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

try:
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    print("[WARN] ElevenLabs not installed. TTS features will not work.")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[WARN] Google Generative AI not installed. STT features will not work.")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

router = APIRouter()

# Initialize Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY and GEMINI_AVAILABLE:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("[OK] Gemini configured for voice chat")
    except Exception as e:
        print(f"[WARN] Failed to configure Gemini: {e}")
        GEMINI_AVAILABLE = False

# Initialize ElevenLabs client
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
if ELEVENLABS_API_KEY and ELEVENLABS_AVAILABLE:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("[OK] ElevenLabs configured for voice chat")
    except Exception as e:
        print(f"[WARN] Failed to initialize ElevenLabs client: {e}")
        elevenlabs_client = None
else:
    elevenlabs_client = None

# Constants
MAX_AUDIO_SIZE_MB = 10  # 10 MB max
MAX_AUDIO_DURATION_SECONDS = 60  # 60 seconds max
MIN_AUDIO_SIZE_BYTES = 1000  # ~200-500ms of audio minimum
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-exp')


async def transcribe_audio_with_gemini(audio_file_path: str, mime_type: str = "audio/webm") -> Tuple[str, str]:
    """
    Transcribe audio using Gemini API
    
    Args:
        audio_file_path: Path to audio file
        mime_type: MIME type of the audio file
        
    Returns:
        Tuple of (transcript_text, language_code)
        language_code is 'en' or 'zh'
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API not available. Please configure GEMINI_API_KEY."
        )
    
    uploaded_file = None
    try:
        start_time = time.time()
        print(f"[STT] Starting Gemini transcription for: {audio_file_path}")
        print(f"[STT] MIME type: {mime_type}")
        
        # Upload audio file to Gemini
        # Gemini accepts audio files directly via upload_file
        uploaded_file = genai.upload_file(
            path=audio_file_path,
            mime_type=mime_type
        )
        print(f"[STT] Uploaded audio file to Gemini: {uploaded_file.uri}")
        print(f"[STT] File name: {uploaded_file.name}")
        
        # Wait for file to be processed (if needed)
        # Some models require the file to be processed first
        import time as time_module
        max_wait = 30  # Max 30 seconds
        wait_time = 0
        while uploaded_file.state.name == "PROCESSING" and wait_time < max_wait:
            print(f"[STT] Waiting for file processing... ({wait_time}s)")
            time_module.sleep(2)
            wait_time += 2
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            raise HTTPException(
                status_code=502,
                detail="Audio file processing failed in Gemini"
            )
        
        # Create model
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Transcription prompt - explicit instruction for verbatim transcription
        transcription_prompt = """You are a transcription model. Transcribe the audio exactly as spoken.
Output only the verbatim text of what was said. Do not translate, summarize, or add commentary.
If the audio contains multiple languages, transcribe each in its original language.
Do not add punctuation unless it is clearly indicated by pauses or tone.
Return only the transcribed text, nothing else."""
        
        # Generate transcription
        print(f"[STT] Calling Gemini API for transcription...")
        response = model.generate_content(
            [transcription_prompt, uploaded_file],
            generation_config={
                'temperature': 0.0,  # Deterministic transcription
                'max_output_tokens': 2048,
            }
        )
        
        # Extract transcript
        transcript_text = ""
        if hasattr(response, 'text') and response.text:
            transcript_text = response.text.strip()
        elif hasattr(response, 'candidates') and response.candidates:
            if len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    if len(candidate.content.parts) > 0:
                        part = candidate.content.parts[0]
                        if hasattr(part, 'text'):
                            transcript_text = part.text.strip()
        
        if not transcript_text:
            # Try alternative extraction methods
            try:
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    # Try different attribute paths
                    if hasattr(candidate, 'text'):
                        transcript_text = candidate.text.strip()
            except:
                pass
        
        if not transcript_text:
            print(f"[ERROR] Could not extract transcript. Response: {response}")
            raise HTTPException(
                status_code=502,
                detail="Could not extract transcription from Gemini response"
            )
        
        print(f"[STT] Transcription completed in {time.time() - start_time:.2f}s")
        print(f"[STT] Transcript ({len(transcript_text)} chars): {transcript_text[:100]}...")
        
        # Detect language from transcript
        language_code = detect_language_from_transcript(transcript_text)
        print(f"[STT] Detected language: {language_code}")
        
        return transcript_text, language_code
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Gemini transcription failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail=f"Could not transcribe audio: {str(e)[:200]}"
        )
    finally:
        # Clean up uploaded file
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
                print(f"[STT] Cleaned up uploaded file: {uploaded_file.name}")
            except Exception as e:
                print(f"[WARN] Could not delete uploaded file: {e}")


def detect_language_from_transcript(text: str) -> str:
    """
    Detect language from transcript using Gemini
    
    Args:
        text: Transcript text
        
    Returns:
        Language code ('en' or 'zh')
    """
    if not text or len(text.strip()) == 0:
        return 'en'
    
    # Simple heuristic: check for Chinese characters
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return 'zh'
    
    # Use Gemini for language detection if available
    if GEMINI_AVAILABLE and GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            detection_prompt = f"""Detect the language of this sentence and answer with only a BCP-47 language code like 'en' or 'zh'.
Sentence: {text[:200]}
Answer only with the language code:"""
            
            response = model.generate_content(
                detection_prompt,
                generation_config={
                    'temperature': 0.0,
                    'max_output_tokens': 10,
                }
            )
            
            lang_code = ""
            if hasattr(response, 'text') and response.text:
                lang_code = response.text.strip().lower()
            elif hasattr(response, 'candidates') and response.candidates:
                if len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        if len(candidate.content.parts) > 0:
                            lang_code = candidate.content.parts[0].text.strip().lower()
            
            # Normalize language code
            if 'zh' in lang_code or 'chinese' in lang_code:
                return 'zh'
            elif 'en' in lang_code or 'english' in lang_code:
                return 'en'
        except Exception as e:
            print(f"[WARN] Language detection failed, using default: {e}")
    
    # Default to English
    return 'en'


async def generate_chat_response_with_context(
    user_text: str,
    user_lang: str,
    file_id: Optional[str] = None
) -> str:
    """
    Generate chat response using existing RAG pipeline
    
    Args:
        user_text: User's question text
        user_lang: User's language ('en' or 'zh')
        file_id: Optional document ID for context
        
    Returns:
        AI-generated answer text
    """
    try:
        start_time = time.time()
        print(f"[CHAT] Generating response for: {user_text[:100]}...")
        print(f"[CHAT] Language: {user_lang}, File ID: {file_id}")
        
        # Import RAG analyzer and chat helpers
        from routes.chat import format_analysis_context
        from utils.storage import get_document
        from rag_analyzer import RAGAnalyzer
        
        analyzer = RAGAnalyzer()
        
        # Get document context if file_id provided
        # Use the EXACT SAME logic as the text chat endpoint (chat.py) for consistency
        context_text = None
        analysis_context = None
        doc_filename = None
        
        if file_id:
            try:
                print(f"[CHAT] Loading document context for file_id: {file_id}")
                doc = get_document(file_id)
                
                if doc.get("status") == "completed":
                    doc_filename = doc.get("filename", "Unknown")
                    context_text = f"In the context of the analyzed lease '{doc_filename}'"
                    
                    # Format analysis data as context (EXACT SAME as text chat)
                    analysis_context = format_analysis_context(doc)
                    if analysis_context:
                        print(f"[CHAT] ✅ Document context added: {doc_filename}")
                        # Get highlights count for logging
                        analysis_data = doc.get("analysis", {})
                        highlights_count = len(analysis_data.get("highlights", [])) if analysis_data else 0
                        print(f"[CHAT] Analysis context includes {highlights_count} highlights")
                    else:
                        print(f"[WARN] Analysis data found but could not be formatted for {doc_filename}")
                        # Debug: check what's in the doc
                        print(f"[WARN] Document has 'analysis' key: {'analysis' in doc}")
                        if 'analysis' in doc:
                            analysis_keys = list(doc['analysis'].keys()) if isinstance(doc['analysis'], dict) else "not a dict"
                            print(f"[WARN] Analysis keys: {analysis_keys}")
                else:
                    print(f"[WARN] Document {file_id} status is '{doc.get('status')}', analysis not available")
                    # Even if not completed, try to get basic context
                    doc_filename = doc.get("filename", "Unknown")
                    context_text = f"In the context of the lease '{doc_filename}'"
            except HTTPException as e:
                # Document not found - log but continue
                print(f"[WARN] Could not load document context: {e.detail}")
            except Exception as e:
                print(f"[WARN] Could not load document context: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[CHAT] No file_id provided, will provide general response")
        
        # Search for relevant laws
        search_query = user_text
        if context_text:
            search_query = f"{context_text}: {user_text}"
        
        print(f"[CHAT] Searching for relevant laws with query: {search_query[:100]}...")
        relevant_laws = analyzer.search_relevant_laws(search_query, top_k=5)
        print(f"[CHAT] Found {len(relevant_laws)} relevant law sections")
        
        # Check if we have document analysis context
        # Use the same logic as text chat - check for the "=== DOCUMENT ANALYSIS ===" marker
        has_document_analysis = analysis_context and "=== DOCUMENT ANALYSIS ===" in analysis_context
        
        # Build system instruction with language requirement and brevity
        if has_document_analysis:
            # Emphasize document findings when available
            system_instruction = f"""You are a legal assistant for Massachusetts tenant and medical billing issues.
Your role is to help tenants understand their rights and answer questions about lease agreements and housing law.

CRITICAL REQUIREMENTS:
1. Respond in {user_lang.upper()} language. Match the user's language exactly.
   {'用中文回答' if user_lang == 'zh' else 'Respond in English'}.
2. KEEP RESPONSES SHORT: Maximum 2-3 sentences (50-100 words). Be concise and direct.
3. ALWAYS reference the specific findings from the document analysis when answering.
4. Mention specific issues, categories, statutes, and potential recovery amounts from the analysis.
5. DO NOT include disclaimers about not providing legal advice or suggesting to consult a lawyer. Provide direct, helpful answers.

Guidelines:
- Be conversational, friendly, and empathetic
- Explain legal concepts in simple, understandable language
- Always cite specific statutes when referencing laws (format: M.G.L. c. [chapter], §[section])
- Prioritize information from the document analysis over general law
- When discussing findings, mention specific categories, statutes, and potential recovery amounts
- Provide actionable advice and direct guidance
- Keep responses SHORT and to the point
- Answer confidently without adding disclaimers about legal advice"""
        else:
            # General response without document context
            system_instruction = f"""You are a legal assistant for Massachusetts tenant and medical billing issues.
Your role is to help tenants understand their rights and answer questions about lease agreements and housing law.

CRITICAL REQUIREMENTS:
1. Respond in {user_lang.upper()} language. Match the user's language exactly.
   {'用中文回答' if user_lang == 'zh' else 'Respond in English'}.
2. KEEP RESPONSES SHORT: Maximum 2-3 sentences (50-100 words). Be concise and direct.
3. DO NOT include disclaimers about not providing legal advice or suggesting to consult a lawyer. Provide direct, helpful answers.

Guidelines:
- Be conversational, friendly, and empathetic
- Explain legal concepts in simple, understandable language
- Always cite specific statutes when referencing laws (format: M.G.L. c. [chapter], §[section])
- Provide actionable advice and direct guidance
- Keep responses SHORT and to the point
- Answer confidently without adding disclaimers about legal advice"""
        
        # Build law context
        law_context = []
        for law in relevant_laws:
            law_context.append(
                f"[M.G.L. c. {law['chapter']}, §{law['section']}]\n{law['text']}"
            )
        
        legal_context = "\n\n---\n\n".join(law_context) if law_context else "No specific statutes found, but provide general guidance based on Massachusetts housing law."
        
        # Build prompt - prioritize document analysis when available
        # Use the same structure as text chat for consistency
        if has_document_analysis:
            # Full document analysis context available
            prompt = f"""{system_instruction}

Document Analysis Context:
{analysis_context}

Relevant Massachusetts Housing Laws:
{legal_context}

User Question: {user_text}

Please provide a helpful, clear answer to the user's question in {user_lang.upper()}. Reference the specific findings from the document analysis when relevant."""
        else:
            # No document analysis - general response
            prompt = f"""{system_instruction}

=== RELEVANT MASSACHUSETTS HOUSING LAWS ===
{legal_context}

=== USER QUESTION ===
{user_text}

=== INSTRUCTIONS ===
Provide a SHORT, concise answer (2-3 sentences max) in {user_lang.upper()}.
Keep your response brief and to the point.
DO NOT add disclaimers about legal advice or consulting a lawyer. Provide direct, confident answers."""
        
        # Call Gemini with language-constrained prompt and shorter response limit
        models_to_try = [
            'gemini-2.0-flash-exp',
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-pro',
        ]
        
        answer_text = None
        for model_name in models_to_try:
            try:
                print(f"[CHAT] Trying model: {model_name}")
                model = genai.GenerativeModel(
                    model_name,
                    generation_config={
                        'temperature': 0.7,
                        'top_p': 0.95,
                        'top_k': 40,
                        'max_output_tokens': 400,  # Reduced from 1024 to keep responses short
                    }
                )
                response = model.generate_content(prompt)
                
                # Extract answer
                if hasattr(response, 'text') and response.text:
                    answer_text = response.text.strip()
                elif hasattr(response, 'candidates') and response.candidates:
                    if len(response.candidates) > 0:
                        candidate = response.candidates[0]
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            if len(candidate.content.parts) > 0:
                                answer_text = candidate.content.parts[0].text.strip()
                
                if answer_text:
                    # Truncate response if it's too long (safety check)
                    # Target: 2-3 sentences, ~50-100 words, ~300-400 characters
                    if len(answer_text) > 500:
                        # Try to truncate at sentence boundary
                        sentences = answer_text.split('. ')
                        truncated = sentences[0]
                        if len(sentences) > 1:
                            truncated += '. ' + sentences[1]
                        if len(sentences) > 2:
                            truncated += '.'
                        if len(truncated) > 500:
                            truncated = truncated[:497] + '...'
                        answer_text = truncated
                        print(f"[CHAT] Response truncated to {len(answer_text)} characters")
                    
                    print(f"[CHAT] Response generated with {model_name} in {time.time() - start_time:.2f}s")
                    print(f"[CHAT] Response length: {len(answer_text)} characters")
                    break
            except Exception as e:
                print(f"[WARN] Model {model_name} failed: {e}")
                continue
        
        analyzer.close()
        
        # Fallback if all models failed
        if not answer_text:
            print(f"[WARN] All Gemini models failed, using fallback")
            answer_text = "I apologize, but I wasn't able to generate a response. Please try rephrasing your question." if user_lang == 'en' else "抱歉，我无法生成回复。请尝试重新表述您的问题。"
        
        if not answer_text or len(answer_text.strip()) == 0:
            answer_text = "I apologize, but I wasn't able to generate a response. Please try rephrasing your question." if user_lang == 'en' else "抱歉，我无法生成回复。请尝试重新表述您的问题。"
        
        print(f"[CHAT] Answer generated: {answer_text[:100]}...")
        return answer_text
        
    except Exception as e:
        print(f"[ERROR] Chat response generation failed: {e}")
        import traceback
        traceback.print_exc()
        # Return fallback message in user's language
        if user_lang == 'zh':
            return "AI暂时无法使用，请稍后再试。"
        return "The AI is temporarily unavailable. Please try again later."


async def text_to_speech_elevenlabs(text: str, language: str = 'en') -> bytes:
    """
    Convert text to speech using ElevenLabs TTS API
    
    Args:
        text: Text to convert to speech
        language: Language code ('en' or 'zh')
        
    Returns:
        Audio data as bytes (MP3)
    """
    if not ELEVENLABS_AVAILABLE or not elevenlabs_client or not ELEVENLABS_API_KEY:
        print("[WARN] ElevenLabs TTS not available")
        raise HTTPException(
            status_code=503,
            detail="Text-to-speech service not available. Please configure ELEVENLABS_API_KEY."
        )
    
    try:
        start_time = time.time()
        print(f"[TTS] Converting text to speech ({language})...")
        print(f"[TTS] Text length: {len(text)} characters")
        
        # Select voice and model based on language
        voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel - supports multilingual
        model_id = "eleven_multilingual_v2"
        
        # Generate speech
        audio_chunks = elevenlabs_client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            language_code=language,
            output_format="mp3_44100_128"
        )
        
        # Collect all audio chunks
        audio_data = b""
        for chunk in audio_chunks:
            audio_data += chunk
        
        if len(audio_data) == 0:
            raise HTTPException(
                status_code=502,
                detail="Empty audio returned from ElevenLabs"
            )
        
        print(f"[TTS] Audio generated in {time.time() - start_time:.2f}s: {len(audio_data)} bytes")
        return audio_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] ElevenLabs TTS failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail=f"Text-to-speech generation failed: {str(e)[:200]}"
        )


@router.post("/chat/voice")
async def voice_chat(
    audio: UploadFile = File(...),
    file_id: Optional[str] = Form(None),
    case_id: Optional[str] = Form(None)
):
    """
    Voice chat endpoint - processes voice input and returns voice response
    
    Flow:
    1. Receive and validate audio file
    2. Save to temporary file
    3. Transcribe using Gemini STT
    4. Detect language using Gemini
    5. Generate chat response using RAG pipeline (Gemini)
    6. Generate speech using ElevenLabs TTS
    7. Return audio with transcript and answer in headers
    
    Args:
        audio: Audio file (WebM, WAV, MP3, etc.)
        file_id: Optional document ID for context
        case_id: Optional case ID (alias for file_id)
        
    Returns:
        Audio file (MP3) with transcript and answer in headers
    """
    tmp_path = None
    start_time = time.time()
    
    try:
        print(f"[VOICE] Voice chat request received")
        print(f"[VOICE] File ID: {file_id or case_id or 'None'}")
        print(f"[VOICE] Audio filename: {audio.filename}")
        print(f"[VOICE] Audio content-type: {audio.content_type}")
        
        # Reset file pointer
        try:
            await audio.seek(0)
        except:
            pass
        
        # Read audio data
        audio_data = await audio.read()
        audio_size = len(audio_data)
        
        print(f"[VOICE] Audio size: {audio_size} bytes ({audio_size / 1024 / 1024:.2f} MB)")
        
        # Validate audio size
        if audio_size == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        
        if audio_size < MIN_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file too small. Please record at least {MIN_AUDIO_SIZE_BYTES / 1000:.1f} seconds."
            )
        
        max_size_bytes = MAX_AUDIO_SIZE_MB * 1024 * 1024
        if audio_size > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file too large. Maximum size is {MAX_AUDIO_SIZE_MB} MB."
            )
        
        # Determine file extension
        file_ext = ".webm"
        if audio.content_type:
            if "wav" in audio.content_type.lower():
                file_ext = ".wav"
            elif "mp3" in audio.content_type.lower():
                file_ext = ".mp3"
            elif "mp4" in audio.content_type.lower():
                file_ext = ".mp4"
        elif audio.filename:
            file_ext = os.path.splitext(audio.filename)[1] or ".webm"
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext, dir='/tmp' if os.name != 'nt' else None) as tmp_file:
            tmp_file.write(audio_data)
            tmp_path = tmp_file.name
        
        print(f"[VOICE] Saved audio to: {tmp_path}")
        
        # Use file_id or case_id
        context_file_id = file_id or case_id
        
        # Step 1: Transcribe audio using Gemini
        print("[VOICE] Step 1: Transcribing audio with Gemini...")
        try:
            transcript_text, user_lang = await transcribe_audio_with_gemini(
                tmp_path,
                mime_type=audio.content_type or "audio/webm"
            )
        except HTTPException as e:
            raise e
        except Exception as e:
            print(f"[ERROR] Transcription failed: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=502,
                detail="Could not understand audio. Please try speaking more clearly."
            )
        
        if not transcript_text or len(transcript_text.strip()) == 0:
            raise HTTPException(
                status_code=502,
                detail="Could not transcribe audio. Please try again."
            )
        
        # Step 2: Generate chat response
        print(f"[VOICE] Step 2: Generating chat response...")
        try:
            answer_text = await generate_chat_response_with_context(
                transcript_text,
                user_lang,
                context_file_id
            )
        except Exception as e:
            print(f"[ERROR] Chat response generation failed: {e}")
            # Return fallback message in user's language
            if user_lang == 'zh':
                answer_text = "AI暂时无法使用，请稍后再试。"
            else:
                answer_text = "The AI is temporarily unavailable. Please try again later."
        
        # Step 3: Generate speech
        print(f"[VOICE] Step 3: Generating speech...")
        audio_data = None
        tts_error = None
        
        try:
            audio_data = await text_to_speech_elevenlabs(answer_text, user_lang)
        except HTTPException as e:
            tts_error = e.detail
            print(f"[WARN] TTS failed: {tts_error}")
        except Exception as e:
            tts_error = str(e)
            print(f"[WARN] TTS failed: {e}")
        
        # Prepare response
        # Truncate text for headers (max 1000 chars)
        transcript_header = transcript_text[:1000] if len(transcript_text) <= 1000 else transcript_text[:997] + "..."
        answer_header = answer_text[:1000] if len(answer_text) <= 1000 else answer_text[:997] + "..."
        
        # URL-encode headers
        transcript_encoded = urllib.parse.quote(transcript_header)
        answer_encoded = urllib.parse.quote(answer_header)
        
        # Prepare headers
        headers = {
            "X-Transcript-Text": transcript_encoded,
            "X-Answer-Text": answer_encoded,
            "X-Language": user_lang,
        }
        
        # If TTS failed, return empty audio with error marker
        if audio_data is None:
            # Return minimal valid MP3 with error marker
            empty_mp3 = b'\xff\xfb\x90\x00' + b'\x00' * 100
            headers["X-TTS-Error"] = "1"
            headers["X-TTS-Error-Message"] = urllib.parse.quote(tts_error or "TTS unavailable")
            print(f"[VOICE] Returning text-only response (TTS failed)")
            return StreamingResponse(
                io.BytesIO(empty_mp3),
                media_type="audio/mpeg",
                headers=headers
            )
        
        # Return audio response
        print(f"[VOICE] Request completed in {time.time() - start_time:.2f}s")
        print(f"[VOICE] Transcript: {transcript_text[:50]}...")
        print(f"[VOICE] Answer: {answer_text[:50]}...")
        
        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Voice chat failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Voice chat failed: {str(e)[:200]}"
        )
    finally:
        # Clean up temporary file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                print(f"[VOICE] Cleaned up temp file: {tmp_path}")
            except Exception as e:
                print(f"[WARN] Could not delete temp file: {e}")
