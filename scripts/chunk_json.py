import json
import re
from typing import List, Dict

def estimate_tokens(text: str) -> int:
    """
    Estimate token count using a simple heuristic.
    Rule of thumb: ~4 characters per token for English text.
    This is a conservative estimate that works well for most tokenizers.
    """
    return len(text) // 4

def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Split on period, exclamation, question mark followed by space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def chunk_text(text: str, max_tokens: int = 6000) -> List[str]:
    """
    Chunk text into smaller pieces that don't exceed max_tokens.
    Tries to maintain sentence boundaries.
    """
    current_tokens = estimate_tokens(text)
    
    # If already under limit, return as is
    if current_tokens <= max_tokens:
        return [text]
    
    # Split into sentences and combine into chunks
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = []
    current_chunk_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = estimate_tokens(sentence)
        
        # If a single sentence exceeds max_tokens, we need to split it further
        if sentence_tokens > max_tokens:
            # If current chunk has content, save it first
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_chunk_tokens = 0
            
            # Split long sentence into words and chunk those
            words = sentence.split()
            word_chunk = []
            word_chunk_tokens = 0
            
            for word in words:
                word_tokens = estimate_tokens(word + ' ')
                if word_chunk_tokens + word_tokens > max_tokens:
                    chunks.append(' '.join(word_chunk))
                    word_chunk = [word]
                    word_chunk_tokens = word_tokens
                else:
                    word_chunk.append(word)
                    word_chunk_tokens += word_tokens
            
            if word_chunk:
                chunks.append(' '.join(word_chunk))
        
        # If adding this sentence would exceed max_tokens, start a new chunk
        elif current_chunk_tokens + sentence_tokens > max_tokens:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_chunk_tokens = sentence_tokens
        else:
            current_chunk.append(sentence)
            current_chunk_tokens += sentence_tokens
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def chunk_json_file(input_file: str, output_file: str, max_tokens: int = 6000):
    """
    Process a JSON file and chunk any text fields that exceed max_tokens.
    Each chunk becomes a separate entry in the output JSON.
    """
    print(f"\nProcessing {input_file}...")
    
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    chunked_data = []
    total_chunks = 0
    sections_chunked = 0
    
    for item in data:
        text = item.get('text', '')
        text_tokens = estimate_tokens(text)
        
        # If text is under limit, add consistent fields
        if text_tokens <= max_tokens:
            chunked_item = item.copy()
            chunked_item['chunk_index'] = 1
            chunked_item['total_chunks'] = 1
            chunked_data.append(chunked_item)
        else:
            # Chunk the text
            sections_chunked += 1
            text_chunks = chunk_text(text, max_tokens)
            total_chunks += len(text_chunks)
            
            print(f"  Section {item.get('section', 'unknown')}: {text_tokens} tokens -> {len(text_chunks)} chunks")
            
            # Create a new entry for each chunk
            for i, chunk in enumerate(text_chunks, 1):
                chunked_item = item.copy()
                chunked_item['text'] = chunk
                chunked_item['chunk_index'] = i
                chunked_item['total_chunks'] = len(text_chunks)
                chunked_data.append(chunked_item)
    
    # Save chunked data
    with open(output_file, 'w') as f:
        json.dump(chunked_data, f, indent=2)
    
    print(f"  Original sections: {len(data)}")
    print(f"  Sections requiring chunking: {sections_chunked}")
    print(f"  Total output entries: {len(chunked_data)}")
    print(f"  Saved to {output_file}")
    
    return len(data), sections_chunked, len(chunked_data)

def main():
    files_to_process = [
        ('chapter_186.json', 'chapter_186_chunked.json'),
        ('chapter_93A.json', 'chapter_93A_chunked.json')
    ]
    
    print("=" * 60)
    print("Chunking JSON files for RAG/Embedding compatibility")
    print("Maximum tokens per chunk: 6000")
    print("=" * 60)
    
    total_original = 0
    total_chunked_sections = 0
    total_output = 0
    
    for input_file, output_file in files_to_process:
        try:
            original, chunked, output = chunk_json_file(input_file, output_file)
            total_original += original
            total_chunked_sections += chunked
            total_output += output
        except FileNotFoundError:
            print(f"  Error: {input_file} not found, skipping...")
        except Exception as e:
            print(f"  Error processing {input_file}: {e}")
    
    print("\n" + "=" * 60)
    print(f"SUMMARY:")
    print(f"  Total original sections: {total_original}")
    print(f"  Sections that needed chunking: {total_chunked_sections}")
    print(f"  Total output entries (including chunks): {total_output}")
    print("=" * 60)

if __name__ == "__main__":
    main()

