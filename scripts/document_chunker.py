"""
Document chunking module
"""
import re
from typing import List, Dict


class DocumentChunker:
    """Chunk documents into smaller pieces for analysis"""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count (4 chars ≈ 1 token)"""
        return len(text) // 4
    
    def chunk_document(self, text: str, max_tokens: int = 4000, overlap: int = 200) -> List[Dict]:
        """
        Chunk document text into smaller pieces with overlap.
        Overlap helps maintain context between chunks.
        
        Args:
            text: Document text
            max_tokens: Maximum tokens per chunk
            overlap: Token overlap between chunks
            
        Returns:
            List of chunks with metadata
        """
        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = self.estimate_tokens(para)
            
            # If single paragraph exceeds max, split it by sentences
            if para_tokens > max_tokens:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sentence in sentences:
                    sentence_tokens = self.estimate_tokens(sentence)
                    
                    if current_tokens + sentence_tokens > max_tokens:
                        if current_chunk:
                            chunk_text = ' '.join(current_chunk)
                            chunks.append({
                                'text': chunk_text,
                                'tokens': self.estimate_tokens(chunk_text),
                                'chunk_index': len(chunks) + 1
                            })
                            # Keep last few sentences for overlap
                            overlap_text = ' '.join(current_chunk[-2:]) if len(current_chunk) >= 2 else ''
                            current_chunk = [overlap_text, sentence] if overlap_text else [sentence]
                            current_tokens = self.estimate_tokens(' '.join(current_chunk))
                        else:
                            current_chunk = [sentence]
                            current_tokens = sentence_tokens
                    else:
                        current_chunk.append(sentence)
                        current_tokens += sentence_tokens
            
            # If adding this paragraph would exceed max, save current chunk
            elif current_tokens + para_tokens > max_tokens:
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    chunks.append({
                        'text': chunk_text,
                        'tokens': self.estimate_tokens(chunk_text),
                        'chunk_index': len(chunks) + 1
                    })
                    # Keep last paragraph for overlap
                    overlap_text = current_chunk[-1] if current_chunk else ''
                    current_chunk = [overlap_text, para] if overlap_text else [para]
                    current_tokens = self.estimate_tokens(' '.join(current_chunk))
                else:
                    current_chunk = [para]
                    current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens
        
        # Add final chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append({
                'text': chunk_text,
                'tokens': self.estimate_tokens(chunk_text),
                'chunk_index': len(chunks) + 1
            })
        
        # Add total_chunks to all
        total = len(chunks)
        for chunk in chunks:
            chunk['total_chunks'] = total
        
        print(f"\n📦 Created {len(chunks)} chunks from document")
        for chunk in chunks:
            print(f"   Chunk {chunk['chunk_index']}/{chunk['total_chunks']}: {chunk['tokens']} tokens")
        
        return chunks

