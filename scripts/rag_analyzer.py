"""
RAG Analyzer - Handles Snowflake vector search and Gemini AI analysis
"""
import snowflake.connector
import google.generativeai as genai
from dotenv import load_dotenv
import os
import json
import numpy as np
import re
from typing import List, Dict, Optional
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))


class RAGAnalyzer:
    """RAG-based legal analysis using Snowflake and Gemini"""
    
    def __init__(self):
        """Initialize Snowflake connection"""
        self.conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
            database=os.getenv('SNOWFLAKE_DATABASE'),
            schema=os.getenv('SNOWFLAKE_SCHEMA')
        )
        self.cursor = self.conn.cursor()
        print("✓ Connected to Snowflake")
    
    def extract_metadata(self, lease_text: str, file_path: str = None) -> Dict:
        """
        Extract document metadata using Gemini (Stage 1 of analysis)
        
        Args:
            lease_text: Full text of the lease document
            file_path: Path to the PDF file (for getting page count)
            
        Returns:
            Dictionary with extracted metadata
        """
        print("📋 Extracting document metadata...")
        
        # Create metadata extraction prompt
        prompt = f"""You are a legal document analyzer. Extract the following metadata from this lease agreement.

LEASE DOCUMENT:
{lease_text[:10000]}  

Extract and return the following information in JSON format:
{{
    "fileName": "descriptive name based on property/parties",
    "documentType": "type of lease (e.g., Commercial Lease Agreement, Residential Lease, etc.)",
    "parties": {{
        "landlord": "landlord name or entity",
        "tenant": "tenant name or [REDACTED] if not visible",
        "property": "full property address"
    }},
    "leaseDetails": {{
        "leaseType": "Commercial or Residential",
        "propertyAddress": "full address",
        "leaseTerm": "term description (e.g., '12 months', 'month-to-month', '3 years with renewal option')",
        "monthlyRent": "rent amount or description (e.g., '$2,500', 'Variable - see base rent clause')",
        "securityDeposit": "deposit amount or 'Not specified'",
        "specialClauses": ["list of notable clauses found, e.g., 'AS-IS condition', 'Broad indemnification', etc."]
    }}
}}

Be thorough and extract as much information as possible. If information is not found, use "Not specified" or appropriate placeholder.
Return ONLY valid JSON, no additional text."""

        try:
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content(prompt)
            
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            metadata = json.loads(response_text)
            
            # Get page count if file_path provided
            page_count = None
            file_size = None
            if file_path and os.path.exists(file_path):
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        page_count = len(pdf_reader.pages)
                    file_size = os.path.getsize(file_path)
                except Exception as e:
                    print(f"⚠️  Could not read PDF metadata: {e}")
            
            # Add file metadata
            metadata['pageCount'] = page_count
            metadata['fileSize'] = f"{file_size // 1024} KB" if file_size else "Unknown"
            metadata['uploadDate'] = datetime.now().strftime("%Y-%m-%d")
            
            print(f"✅ Metadata extraction complete")
            return metadata
            
        except json.JSONDecodeError as e:
            print(f"⚠️  Warning: Could not parse metadata JSON: {e}")
            # Return default metadata structure
            return {
                "fileName": "Unknown Document",
                "documentType": "Lease Agreement",
                "parties": {
                    "landlord": "Not specified",
                    "tenant": "Not specified",
                    "property": "Not specified"
                },
                "leaseDetails": {
                    "leaseType": "Unknown",
                    "propertyAddress": "Not specified",
                    "leaseTerm": "Not specified",
                    "monthlyRent": "Not specified",
                    "securityDeposit": "Not specified",
                    "specialClauses": []
                },
                "pageCount": None,
                "fileSize": "Unknown",
                "uploadDate": datetime.now().strftime("%Y-%m-%d")
            }
        except Exception as e:
            print(f"⚠️  Metadata extraction error: {e}")
            raise
    
    def search_relevant_laws(self, text: str, top_k: int = 10) -> List[Dict]:
        """
        Search for relevant MA laws using vector similarity
        
        Args:
            text: Query text
            top_k: Number of results to return
            
        Returns:
            List of relevant law sections
        """
        # Get the embedding for the text
        embedding_query = """
        SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0', %s) as embedding
        """
        
        self.cursor.execute(embedding_query, (text,))
        text_embedding = np.array(self.cursor.fetchone()[0])
        
        # Get all legal documents with their embeddings
        query = """
        SELECT 
            id,
            chapter,
            section,
            section_title,
            text,
            chunk_index,
            total_chunks,
            text_embedding
        FROM legal_documents
        WHERE text_embedding IS NOT NULL
        """
        
        self.cursor.execute(query)
        
        # Compute similarities locally
        results = []
        for row in self.cursor:
            doc_embedding = np.array(row[7])
            
            # Cosine similarity
            similarity = np.dot(text_embedding, doc_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(doc_embedding)
            )
            
            results.append({
                'id': row[0],
                'chapter': row[1],
                'section': row[2],
                'section_title': row[3],
                'text': row[4],
                'chunk_index': row[5],
                'total_chunks': row[6],
                'similarity': similarity
            })
        
        # Sort by similarity (highest first) and return top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def analyze_chunk(self, lease_chunk: Dict, relevant_laws: List[Dict]) -> Dict:
        """
        Analyze a single chunk of the lease against MA laws
        
        Args:
            lease_chunk: Chunk to analyze
            relevant_laws: Relevant law sections
            
        Returns:
            Analysis results
        """
        # Prepare legal context
        law_context = []
        for law in relevant_laws:
            law_context.append(
                f"[Chapter {law['chapter']}, {law['section']}]\n{law['text']}"
            )
        
        context = "\n\n---\n\n".join(law_context)
        
        # Create analysis prompt
        prompt = f"""You are a legal expert specializing in Massachusetts tenant rights and housing law.

Analyze the following lease agreement clause against Massachusetts General Laws (Chapter 186 - Estates for Years and at Will, and Chapter 93A - Consumer Protection).

LEASE AGREEMENT CLAUSE (Chunk {lease_chunk['chunk_index']}/{lease_chunk['total_chunks']}):
{lease_chunk['text']}

RELEVANT MASSACHUSETTS LAWS:
{context}

Provide a detailed analysis in JSON format with the following structure:
{{
    "illegal_clauses": [
        {{
            "clause": "EXACT VERBATIM text copied word-for-word from the lease above, including all punctuation",
            "violation": "which law/statute it violates",
            "explanation": "why this is illegal",
            "severity": "high/critical",
            "potential_recovery": "estimated dollar amount tenant could recover (e.g., $5000)",
            "recovery_calculation": "detailed explanation of how this amount is calculated under MA law, citing specific statutory remedies"
        }}
    ],
    "risky_terms": [
        {{
            "term": "EXACT VERBATIM text copied word-for-word from the lease above, including all punctuation",
            "risk": "potential legal issue",
            "explanation": "why this could be problematic",
            "severity": "medium/high"
        }}
    ],
    "favorable_clauses": [
        {{
            "clause": "EXACT VERBATIM text copied word-for-word from the lease above, including all punctuation",
            "benefit": "how this protects the tenant",
            "relevant_law": "supporting statute if any"
        }}
    ],
    "concerns": [
        {{
            "issue": "description of concern",
            "recommendation": "what should be done"
        }}
    ]
}}

CRITICAL INSTRUCTIONS FOR TEXT EXTRACTION:
- For the "clause", "term", and "clause" fields, you MUST copy the EXACT text as it appears in the lease above
- Do NOT paraphrase, summarize, or reword the text in any way
- Copy the text VERBATIM, character by character, including all punctuation, capitalization, and spacing
- Include complete sentences or paragraphs that contain the problematic language
- The text you provide will be used to locate the clause in the PDF, so precision is essential

Be thorough and cite specific statutes. If a clause is found in the lease that violates MA law, mark it as illegal.

Common violations and their penalties under Massachusetts law:
- Security deposit violations (Chapter 186, §15B): Up to 3x the deposit amount plus attorney's fees and costs
- Chapter 93A consumer protection violations: Double or triple damages (actual damages × 2 or × 3)
- Illegal exculpatory clauses (Chapter 186, §15): Actual damages plus statutory penalties
- Attorney fee violations (Chapter 186, §20): Attorney's fees if tenant prevails
- Waiver of tenant rights: Actual damages and potential punitive damages
- Improper security deposit handling: $1,000-$5,000 typical range
- Prohibited lease terms (Chapter 186, §15B): Actual damages plus statutory remedies

For each illegal clause, estimate the potential recovery based on:
1. The specific statute violated and its remedies
2. Typical damages awarded in MA courts for similar violations
3. Whether multiple damages (2x, 3x) apply under Chapter 93A
4. Attorney's fees and costs if applicable

Return ONLY valid JSON, no additional text."""

        # Call Gemini for analysis
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        
        # Parse JSON response
        try:
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            analysis = json.loads(response_text)
            return analysis
        except json.JSONDecodeError as e:
            print(f"⚠️  Warning: Could not parse JSON from Gemini response: {e}")
            return {
                "illegal_clauses": [],
                "risky_terms": [],
                "favorable_clauses": [],
                "concerns": [{"issue": "Analysis parsing error", "recommendation": "Manual review recommended"}]
            }
    
    def consolidate_analysis(self, chunk_analyses: List[Dict], full_lease_text: str, 
                           metadata: Dict = None, pii_summary: Dict = None, file_id: str = None, 
                           pdf_path: str = None) -> Dict:
        """
        Consolidate analyses from multiple chunks into a final report with complete structure
        
        Args:
            chunk_analyses: List of analyses from each chunk
            full_lease_text: Full text of the lease
            metadata: Extracted metadata (optional, for enhanced output)
            pii_summary: PII redaction summary (optional)
            file_id: Document ID (optional)
            pdf_path: Path to PDF file for coordinate extraction (optional)
            
        Returns:
            Complete analysis in the required JSON format
        """
        print("📊 Consolidating analysis...")
        
        # Merge all findings
        all_illegal = []
        all_risky = []
        all_favorable = []
        all_concerns = []
        
        for analysis in chunk_analyses:
            all_illegal.extend(analysis.get('illegal_clauses', []))
            all_risky.extend(analysis.get('risky_terms', []))
            all_favorable.extend(analysis.get('favorable_clauses', []))
            all_concerns.extend(analysis.get('concerns', []))
        
        # Calculate metrics
        illegal_count = len(all_illegal)
        risky_count = len(all_risky)
        favorable_count = len(all_favorable)
        
        power_imbalance = min(100, (illegal_count * 20) + (risky_count * 10) - (favorable_count * 5))
        power_imbalance = max(0, power_imbalance)
        
        # Calculate potential recovery
        potential_recovery = 0
        recovery_breakdown = []
        
        for illegal in all_illegal:
            recovery_str = illegal.get('potential_recovery', '')
            recovery_calc = illegal.get('recovery_calculation', '')
            
            # Parse dollar amount
            match = re.search(r'\$?(\d{1,3}(?:,?\d{3})*)', recovery_str)
            if match:
                amount = int(match.group(1).replace(',', ''))
                potential_recovery += amount
                recovery_breakdown.append({
                    'violation': illegal.get('violation', 'Unknown'),
                    'amount': amount,
                    'calculation': recovery_calc
                })
            else:
                # Fallback estimate
                if 'security deposit' in illegal.get('violation', '').lower():
                    amount = 5000
                elif '93a' in illegal.get('violation', '').lower():
                    amount = 2500
                else:
                    amount = 1000
                potential_recovery += amount
                recovery_breakdown.append({
                    'violation': illegal.get('violation', 'Unknown'),
                    'amount': amount,
                    'calculation': recovery_calc or 'Estimated based on violation type'
                })
        
        severity_level = self._get_severity_level(power_imbalance, illegal_count)
        
        # Determine risk level
        if illegal_count >= 3:
            risk_level = "Critical"
        elif illegal_count >= 1:
            risk_level = "High"
        elif risky_count >= 5:
            risk_level = "Medium"
        else:
            risk_level = "Low"
        
        # If enhanced output requested (metadata provided)
        if metadata and file_id and pdf_path:
            print("   Creating highlights with PDF coordinates...")
            
            # Create highlights with PDF coordinates
            highlights = self._create_highlights_with_coordinates(
                all_illegal, all_risky, all_favorable, pdf_path
            )
            
            # Get top issues
            top_issues = []
            for i, illegal in enumerate(all_illegal[:3]):
                top_issues.append({
                    "title": illegal.get('violation', 'Unknown Violation'),
                    "severity": illegal.get('severity', 'high'),
                    "amount": f"${recovery_breakdown[i]['amount']}" if i < len(recovery_breakdown) else "$0"
                })
            
            # Build complete JSON structure
            return {
                "documentId": file_id,
                "pdfUrl": f"/{os.path.basename(pdf_path)}" if pdf_path else "/document.pdf",
                "documentMetadata": {
                    "fileName": metadata.get('fileName', 'Unknown Document'),
                    "uploadDate": metadata.get('uploadDate', datetime.now().strftime("%Y-%m-%d")),
                    "fileSize": metadata.get('fileSize', 'Unknown'),
                    "pageCount": metadata.get('pageCount', 0),
                    "documentType": metadata.get('documentType', 'Lease Agreement'),
                    "parties": metadata.get('parties', {
                        "landlord": "Not specified",
                        "tenant": "Not specified",
                        "property": "Not specified"
                    })
                },
                "deidentificationSummary": {
                    "itemsRedacted": pii_summary.get('total_redactions', 0) if pii_summary else 0,
                    "categories": pii_summary.get('redaction_details', []) if pii_summary else []
                },
                "keyDetailsDetected": {
                    "leaseType": metadata.get('leaseDetails', {}).get('leaseType', 'Unknown'),
                    "propertyAddress": metadata.get('leaseDetails', {}).get('propertyAddress', 'Not specified'),
                    "landlord": metadata.get('parties', {}).get('landlord', 'Not specified'),
                    "leaseTerm": metadata.get('leaseDetails', {}).get('leaseTerm', 'Not specified'),
                    "monthlyRent": metadata.get('leaseDetails', {}).get('monthlyRent', 'Not specified'),
                    "securityDeposit": metadata.get('leaseDetails', {}).get('securityDeposit', 'Not specified'),
                    "specialClauses": metadata.get('leaseDetails', {}).get('specialClauses', [])
                },
                "analysisSummary": {
                    "status": "complete",
                    "summaryText": f"Analysis Complete — {illegal_count} key issues found. " + 
                                  self._generate_summary(illegal_count, risky_count, favorable_count, power_imbalance),
                    "overallRisk": risk_level,
                    "issuesFound": illegal_count,
                    "potential_recovery": potential_recovery,
                    "estimatedRecovery": f"${potential_recovery:,}",
                    "topIssues": top_issues
                },
                "highlights": highlights,
                "document_info": {
                    'total_characters': len(full_lease_text),
                    'total_chunks': len(chunk_analyses),
                    'analysis_date': datetime.now().isoformat()
                }
            }
        else:
            # Legacy format (backward compatibility)
            return {
                "illegal_clauses": all_illegal,
                "risky_terms": all_risky,
                "favorable_clauses": all_favorable,
                "concerns": all_concerns,
                "power_imbalance_score": power_imbalance,
                "potential_recovery_amount": potential_recovery,
                "recovery_breakdown": recovery_breakdown,
                "severity_level": severity_level,
                "summary": self._generate_summary(illegal_count, risky_count, favorable_count, power_imbalance)
            }
    
    def _create_highlights_with_coordinates(self, illegal_clauses: List[Dict], 
                                           risky_terms: List[Dict], 
                                           favorable_clauses: List[Dict],
                                           pdf_path: str) -> List[Dict]:
        """
        Create highlights array with PDF coordinates
        
        Args:
            illegal_clauses: List of illegal clauses
            risky_terms: List of risky terms
            favorable_clauses: List of favorable clauses
            pdf_path: Path to PDF file
            
        Returns:
            List of highlight objects with coordinates
        """
        highlights = []
        highlight_id = 1
        
        # Initialize PDF coordinate extractor
        try:
            from pdf_coordinate_extractor import PDFCoordinateExtractor
            coord_extractor = PDFCoordinateExtractor(pdf_path)
        except Exception as e:
            print(f"⚠️  Could not initialize coordinate extractor: {e}")
            coord_extractor = None
        
        # Add illegal clauses (red highlights)
        for illegal in illegal_clauses:
            text = illegal.get('clause', '')
            
            # Get coordinates
            if coord_extractor:
                position = coord_extractor.find_text_coordinates(text)
            else:
                position = self._get_default_position(1)
            
            highlights.append({
                "id": f"hl-{highlight_id:03d}",
                "pageNumber": position['boundingRect']['pageNumber'],
                "color": "red",
                "priority": 1,
                "category": illegal.get('violation', 'Legal Violation'),
                "text": text,
                "statute": illegal.get('violation', ''),
                "explanation": illegal.get('explanation', ''),
                "damages_estimate": self._parse_amount(illegal.get('potential_recovery', '0')),
                "position": position
            })
            highlight_id += 1
        
        # Add risky terms (orange/yellow highlights)
        for risky in risky_terms:
            text = risky.get('term', '')
            severity = risky.get('severity', 'medium')
            
            if coord_extractor:
                position = coord_extractor.find_text_coordinates(text)
            else:
                position = self._get_default_position(1)
            
            highlights.append({
                "id": f"hl-{highlight_id:03d}",
                "pageNumber": position['boundingRect']['pageNumber'],
                "color": "orange" if severity == "high" else "yellow",
                "priority": 2 if severity == "high" else 3,
                "category": risky.get('risk', 'Risky Term'),
                "text": text,
                "statute": "M.G.L. c. 186",
                "explanation": risky.get('explanation', ''),
                "damages_estimate": 0,
                "position": position
            })
            highlight_id += 1
        
        # Add favorable clauses (green highlights)
        for favorable in favorable_clauses:
            text = favorable.get('clause', '')
            
            if coord_extractor:
                position = coord_extractor.find_text_coordinates(text)
            else:
                position = self._get_default_position(1)
            
            highlights.append({
                "id": f"hl-{highlight_id:03d}",
                "pageNumber": position['boundingRect']['pageNumber'],
                "color": "green",
                "priority": 3,
                "category": favorable.get('benefit', 'Favorable Clause'),
                "text": text,
                "statute": favorable.get('relevant_law', ''),
                "explanation": favorable.get('benefit', ''),
                "damages_estimate": 0,
                "position": position
            })
            highlight_id += 1
        
        if coord_extractor:
            coord_extractor.close()
        
        return highlights
    
    def _parse_amount(self, amount_str: str) -> int:
        """Parse dollar amount from string"""
        match = re.search(r'\$?(\d{1,3}(?:,?\d{3})*)', str(amount_str))
        if match:
            return int(match.group(1).replace(',', ''))
        return 0
    
    def _get_default_position(self, page_num: int) -> Dict:
        """Get default position when coordinates cannot be extracted"""
        return {
            "boundingRect": {
                "x1": 72,
                "y1": 200,
                "x2": 540,
                "y2": 250,
                "pageNumber": page_num
            },
            "rects": [
                {
                    "x1": 72,
                    "y1": 200,
                    "x2": 540,
                    "y2": 250,
                    "pageNumber": page_num
                }
            ]
        }
    
    def _get_severity_level(self, power_score: int, illegal_count: int) -> str:
        """Determine overall severity level"""
        if illegal_count >= 3 or power_score >= 60:
            return "CRITICAL"
        elif illegal_count >= 1 or power_score >= 40:
            return "HIGH"
        elif power_score >= 20:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_summary(self, illegal: int, risky: int, favorable: int, power_score: int) -> str:
        """Generate a human-readable summary"""
        summary_parts = []
        
        if illegal > 0:
            summary_parts.append(f"⚠️  Found {illegal} illegal clause(s) that violate Massachusetts law")
        
        if risky > 0:
            summary_parts.append(f"⚡ Identified {risky} risky term(s) that could be problematic")
        
        if favorable > 0:
            summary_parts.append(f"✓ Found {favorable} tenant-favorable provision(s)")
        
        summary_parts.append(f"Power Imbalance Score: {power_score}/100 {'(Concerning)' if power_score > 50 else '(Acceptable)'}")
        
        return " | ".join(summary_parts)
    
    def generate_chat_response(self, question: str, relevant_laws: List[Dict], context: str = None) -> str:
        """
        Generate chat response using Gemini
        
        Args:
            question: User's question
            relevant_laws: Relevant law sections
            context: Optional context (e.g., document name)
            
        Returns:
            AI-generated answer
        """
        try:
            # Prepare context
            law_context = []
            for law in relevant_laws:
                law_context.append(
                    f"[M.G.L. c. {law['chapter']}, §{law['section']}]\n{law['text']}"
                )
            
            legal_context = "\n\n---\n\n".join(law_context) if law_context else "No specific statutes found, but provide general guidance based on Massachusetts housing law."
            
            # Build a more conversational and helpful prompt
            system_instruction = """You are a friendly and knowledgeable legal assistant specializing in Massachusetts housing and tenant law. 
Your role is to help tenants understand their rights and answer questions about lease agreements and housing law.

Guidelines:
- Be conversational, friendly, and empathetic
- Explain legal concepts in simple, understandable language
- Always cite specific statutes when referencing laws (format: M.G.L. c. [chapter], §[section])
- If document analysis context is provided, reference the specific findings, issues, and highlights from that analysis
- When discussing findings from the document analysis, mention specific categories, statutes, and potential recovery amounts when relevant
- If the question relates to a specific document, reference it naturally and use the analysis data to provide accurate, document-specific answers
- Provide actionable advice when possible
- If you're unsure about something, say so and suggest consulting a lawyer
- Keep responses concise but thorough (2-4 paragraphs typically)"""
            
            # Check if context includes document analysis
            has_document_analysis = context and "=== DOCUMENT ANALYSIS ===" in context
            
            if has_document_analysis:
                prompt = f"""{system_instruction}

Document Analysis Context:
{context}

Relevant Massachusetts Housing Laws:
{legal_context}

User Question: {question}

Please provide a helpful, clear answer to the user's question. Reference the specific findings from the document analysis when relevant, and be conversational and friendly while being accurate about the law."""
            else:
                prompt = f"""{system_instruction}

{context if context else ""}

Relevant Massachusetts Housing Laws:
{legal_context}

User Question: {question}

Please provide a helpful, clear answer to the user's question. Be conversational and friendly while being accurate about the law."""
            
            print(f"🤖 Generating chat response with Gemini for question: {question[:100]}...")
            
            # Try different Gemini models in order of preference
            models_to_try = [
                'gemini-1.5-flash',  # Fast and reliable
                'gemini-1.5-pro',    # More capable
                'gemini-pro',        # Stable fallback
                'gemini-2.0-flash-exp',  # Experimental
            ]
            
            model = None
            response = None
            last_error = None
            
            for model_name in models_to_try:
                try:
                    print(f"   Trying model: {model_name}")
                    # Create generation config as dict
                    generation_config = {
                        'temperature': 0.7,  # Balance between creative and factual
                        'top_p': 0.95,
                        'top_k': 40,
                        'max_output_tokens': 1024,
                    }
                    model = genai.GenerativeModel(
                        model_name,
                        generation_config=generation_config
                    )
                    response = model.generate_content(prompt)
                    print(f"   ✅ Successfully used model: {model_name}")
                    break
                except Exception as e:
                    print(f"   ⚠️  Model {model_name} failed: {e}")
                    last_error = e
                    continue
            
            if not response:
                raise Exception(f"All Gemini models failed. Last error: {last_error}")
            
            # Extract text from response
            answer = None
            if hasattr(response, 'text') and response.text:
                answer = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                if len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        if len(candidate.content.parts) > 0:
                            answer = candidate.content.parts[0].text.strip()
                    elif hasattr(candidate, 'text'):
                        answer = candidate.text.strip()
            
            if not answer:
                # Last resort: try to convert to string
                answer = str(response).strip()
                if not answer or answer.startswith('<'):
                    raise Exception("Could not extract text from Gemini response")
            
            print(f"✅ Generated response ({len(answer)} chars): {answer[:100]}...")
            return answer
            
        except Exception as e:
            print(f"❌ Error generating chat response: {e}")
            # Return a helpful fallback message
            return f"I apologize, but I encountered an error while generating a response. Please try rephrasing your question. Error: {str(e)}"
    
    def close(self):
        """Close Snowflake connection"""
        self.cursor.close()
        self.conn.close()
        print("\n✓ Disconnected from Snowflake")



