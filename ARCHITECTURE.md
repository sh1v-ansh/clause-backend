# Massachusetts Lease Analyzer - Architecture Guide

## 📁 Project Structure

```
Clause/
├── app/                           # Backend API
│   ├── api_v2.py                 # Main FastAPI application (NEW - clean)
│   ├── server.py                 # Server startup script
│   │
│   ├── models/                   # Pydantic models
│   │   ├── __init__.py
│   │   └── requests.py           # Request/response models
│   │
│   ├── routes/                   # API endpoints (modular)
│   │   ├── __init__.py
│   │   ├── upload.py             # File upload endpoints
│   │   ├── analysis.py           # Analysis endpoints
│   │   ├── documents.py          # Document management
│   │   └── chat.py               # Chat/RAG queries
│   │
│   ├── services/                 # Business logic
│   │   ├── __init__.py
│   │   └── analysis_service.py   # Background analysis tasks
│   │
│   ├── utils/                    # Utilities
│   │   ├── __init__.py
│   │   └── storage.py            # Document storage operations
│   │
│   ├── pii_redaction.py          # PII detection & redaction
│   │
│   ├── static/                   # Frontend
│   │   └── index.html            # Web application
│   │
│   ├── data/                     # Runtime data
│   │   ├── documents.json        # Document metadata
│   │   ├── encryption_keys.json  # PII encryption keys
│   │   └── pii_mappings/         # Encrypted PII data
│   │
│   └── uploads/                  # Uploaded PDFs
│
├── scripts/                      # Core analysis modules
│   ├── pdf_extraction.py        # PDF text extraction
│   ├── document_chunker.py      # Document chunking
│   ├── rag_analyzer.py          # RAG & AI analysis
│   │
│   ├── scrape_docs.py           # Legal document scraper
│   ├── chunk_json.py            # JSON chunker
│
├── data/                        # Static legal data
│   ├── chapter_186_chunked.json
│   └── chapter_93A_chunked.json
│
└── requirements.txt             # Dependencies
```

## 🏗️ Architecture Overview

### 1. **API Layer** (`app/`)

#### **Modular Design (api_v2.py - RECOMMENDED)**
```python
FastAPI App
    ├── Routes (endpoints organized by feature)
    │   ├── /upload       → upload.py
    │   ├── /analyze      → analysis.py
    │   ├── /documents    → documents.py
    │   └── /chat         → chat.py
    │
    ├── Services (business logic)
    │   └── analysis_service.py
    │
    ├── Models (data validation)
    │   └── requests.py
    │
    └── Utils (helpers)
        └── storage.py
```

**Benefits:**
- ✅ **Clean separation of concerns**
- ✅ **Easy to test individual components**
- ✅ **Scalable - add new routes without touching existing code**
- ✅ **Maintainable - each file has single responsibility**

#### **Original Design (api.py - DEPRECATED)**
- Single 550+ line file
- All endpoints, logic, and utilities mixed together
- Still functional but harder to maintain

### 2. **Analysis Engine** (`scripts/`)

#### **Modular Design (RECOMMENDED)**

**pdf_extraction.py**
```python
class PDFExtractor:
    - extract_text(pdf_path) → str
```
Single responsibility: Extract text from PDFs

**document_chunker.py**
```python
class DocumentChunker:
    - chunk_document(text, max_tokens) → List[Dict]
    - estimate_tokens(text) → int
```
Single responsibility: Split documents into chunks

**rag_analyzer.py**
```python
class RAGAnalyzer:
    - search_relevant_laws(text, top_k) → List[Dict]
    - analyze_chunk(chunk, laws) → Dict
    - consolidate_analysis(analyses) → Dict
    - generate_chat_response(question, laws) → str
    - close()
```
Single responsibility: RAG operations (Snowflake + Gemini)

**Benefits:**
- ✅ **Each module can be imported independently**
- ✅ **Easy to test individual components**
- ✅ **Reusable across different projects**
- ✅ **Clear interfaces between modules**

#### **Original Design (lease_analyzer.py)**
- Single 558-line file with all functionality
- Still functional but monolithic

### 3. **Data Flow**

```
1. Upload PDF
   ↓
2. PII Redaction (pii_redaction.py)
   - Detects: SSN, emails, names, addresses, etc.
   - Redacts with tokens: [SSN_REDACTED], [NAME_REDACTED]
   - Encrypts mapping for later de-identification
   ↓
3. Text Extraction (pdf_extraction.py)
   - Extracts from redacted text file
   ↓
4. Document Chunking (document_chunker.py)
   - Splits into ~4000 token chunks
   - Maintains overlap for context
   ↓
5. RAG Analysis (rag_analyzer.py)
   For each chunk:
     a. Search Snowflake for relevant laws (vector similarity)
     b. Send chunk + laws to Gemini AI
     c. Get structured analysis (JSON)
   ↓
6. Consolidation (rag_analyzer.py)
   - Merge all chunk analyses
   - Calculate scores
   - Generate summary
   ↓
7. Store Results (utils/storage.py)
   - Save to documents.json
   - Return to frontend
```

## 🔄 Migration Guide

### Using the New Modular API

**1. Update server.py to use api_v2:**
```python
# Old (server.py)
from api import app

# New
from api_v2 import app
```

**2. Start server:**
```bash
cd app
python server.py
```

**3. All endpoints remain the same:**
- ✅ POST /upload
- ✅ POST /analyze
- ✅ GET /status/{file_id}
- ✅ GET /document/{file_id}
- ✅ POST /chat
- ✅ GET /documents
- ✅ DELETE /document/{file_id}

### Using the New Modular Scripts

**Old way:**
```python
from lease_analyzer import LeaseAnalyzer

analyzer = LeaseAnalyzer()
report = analyzer.analyze_lease("lease.pdf")
analyzer.close()
```

**New way:**
```python
from pdf_extraction import PDFExtractor
from document_chunker import DocumentChunker
from rag_analyzer import RAGAnalyzer

# Extract
extractor = PDFExtractor()
text = extractor.extract_text("lease.pdf")

# Chunk
chunker = DocumentChunker()
chunks = chunker.chunk_document(text)

# Analyze
analyzer = RAGAnalyzer()
analyses = []
for chunk in chunks:
    laws = analyzer.search_relevant_laws(chunk['text'])
    analysis = analyzer.analyze_chunk(chunk, laws)
    analyses.append(analysis)

report = analyzer.consolidate_analysis(analyses, text)
analyzer.close()
```

**Or use high-level wrapper (lease_analyzer.py still works):**
```python
from lease_analyzer import LeaseAnalyzer

analyzer = LeaseAnalyzer()
report = analyzer.analyze_lease("lease.pdf")
analyzer.close()
```

## 🎯 When to Use Which?

### Use Modular API (api_v2.py) when:
- ✅ Starting new development
- ✅ Need to add new features
- ✅ Want better code organization
- ✅ Building for production

### Use Original API (api.py) when:
- ⚠️  Quick prototyping
- ⚠️  Don't want to refactor existing code
- ⚠️  Temporary/one-off tasks

### Use Modular Scripts when:
- ✅ Building new tools
- ✅ Need specific functionality (just PDF extraction, just chunking)
- ✅ Want to customize the pipeline
- ✅ Testing individual components

### Use Original lease_analyzer.py when:
- ⚠️  Quick command-line analysis
- ⚠️  Don't need customization
- ⚠️  Simple one-off tasks

## 📊 Comparison

| Feature | Monolithic | Modular |
|---------|-----------|---------|
| **Lines per file** | 550+ | 50-200 |
| **Testability** | Hard | Easy |
| **Reusability** | Low | High |
| **Maintainability** | Low | High |
| **Learning curve** | Simple | Moderate |
| **Scalability** | Limited | Excellent |
| **Performance** | Same | Same |

## 🧪 Testing Individual Modules

### Test PDF Extraction
```python
from pdf_extraction import PDFExtractor

extractor = PDFExtractor()
text = extractor.extract_text("sample.pdf")
print(f"Extracted {len(text)} characters")
```

### Test Document Chunking
```python
from document_chunker import DocumentChunker

chunker = DocumentChunker()
chunks = chunker.chunk_document(text, max_tokens=1000)
print(f"Created {len(chunks)} chunks")
```

### Test RAG Analysis
```python
from rag_analyzer import RAGAnalyzer

analyzer = RAGAnalyzer()
laws = analyzer.search_relevant_laws("security deposit", top_k=3)
for law in laws:
    print(f"{law['chapter']} {law['section']}: {law['similarity']:.2f}")
analyzer.close()
```

### Test PII Redaction
```python
from pii_redaction import PIIRedactor

redactor = PIIRedactor()
text = "John Smith's SSN is 123-45-6789"
redacted, pii = redactor.detect_and_redact(text)
print(f"Redacted: {redacted}")
print(f"Found: {pii}")
```

## 🚀 Adding New Features

### Add a new API endpoint

1. Create route file:
```python
# app/routes/new_feature.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/new-endpoint")
async def new_endpoint():
    return {"message": "New feature"}
```

2. Register in api_v2.py:
```python
from routes import new_feature

app.include_router(new_feature.router, tags=["New Feature"])
```

Done! No need to touch existing code.

### Add a new analysis module

1. Create new file:
```python
# scripts/new_analyzer.py
class NewAnalyzer:
    def analyze(self, data):
        # Your logic
        pass
```

2. Import in analysis_service.py:
```python
from new_analyzer import NewAnalyzer

analyzer = NewAnalyzer()
result = analyzer.analyze(data)
```

## 📝 Best Practices

1. **Keep modules focused** - One responsibility per file
2. **Use clear interfaces** - Well-defined inputs/outputs
3. **Document thoroughly** - Docstrings for all public methods
4. **Test independently** - Each module should be testable
5. **Handle errors gracefully** - Try/except with meaningful messages
6. **Use type hints** - Makes code self-documenting
7. **Follow naming conventions** - snake_case for functions, PascalCase for classes

## 🔧 Troubleshooting

### Import errors
```bash
# Make sure __init__.py files exist
touch app/models/__init__.py
touch app/routes/__init__.py
touch app/utils/__init__.py
touch app/services/__init__.py
```

### Module not found
```python
# Add to sys.path if needed
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
```

### Circular imports
- Keep imports at function level if needed
- Use forward references for type hints
- Restructure if circular dependency exists

## 📚 Next Steps

1. **Migrate to modular API**: Update server.py to use api_v2.py
2. **Add unit tests**: Test each module independently
3. **Add integration tests**: Test complete workflows
4. **Documentation**: API docs, module docs
5. **Monitoring**: Add logging, metrics
6. **Performance**: Profile and optimize hot paths

---

**Status**: ✅ Both architectures fully functional
**Recommendation**: Use modular design for new development
**Backward Compatibility**: Original files still work

