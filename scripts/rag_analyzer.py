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
from typing import List, Dict

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
            "clause": "exact text from lease",
            "violation": "which law/statute it violates",
            "explanation": "why this is illegal",
            "severity": "high/critical",
            "potential_recovery": "estimated dollar amount tenant could recover (e.g., $5000)",
            "recovery_calculation": "detailed explanation of how this amount is calculated under MA law, citing specific statutory remedies"
        }}
    ],
    "risky_terms": [
        {{
            "term": "exact text from lease",
            "risk": "potential legal issue",
            "explanation": "why this could be problematic",
            "severity": "medium/high"
        }}
    ],
    "favorable_clauses": [
        {{
            "clause": "exact text from lease",
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
    
    def consolidate_analysis(self, chunk_analyses: List[Dict], full_lease_text: str) -> Dict:
        """Consolidate analyses from multiple chunks into a final report"""
        
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
        
        # Calculate power imbalance score
        illegal_count = len(all_illegal)
        risky_count = len(all_risky)
        favorable_count = len(all_favorable)
        
        power_imbalance = min(100, (illegal_count * 20) + (risky_count * 10) - (favorable_count * 5))
        power_imbalance = max(0, power_imbalance)
        
        # Calculate potential recovery from AI-provided estimates
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
        # Prepare context
        law_context = []
        for law in relevant_laws:
            law_context.append(
                f"[Chapter {law['chapter']}, {law['section']}]\n{law['text']}"
            )
        
        legal_context = "\n\n---\n\n".join(law_context)
        
        prompt = f"""You are a legal assistant specializing in Massachusetts housing law.
Answer the following question based on the provided legal statutes.

{context if context else ""}

Legal Statutes:
{legal_context}

Question: {question}

Provide a clear, accurate answer with citations to specific statutes."""
        
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        
        return response.text
    
    def close(self):
        """Close Snowflake connection"""
        self.cursor.close()
        self.conn.close()
        print("\n✓ Disconnected from Snowflake")

