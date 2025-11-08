# Massachusetts Lease Analyzer - Backend API Documentation

**Version**: 2.0.0  
**Base URL**: `http://localhost:8000`  
**Architecture**: FastAPI + RAG (Retrieval-Augmented Generation) with Snowflake Vector Search

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Quick Start](#quick-start)
3. [API Endpoints](#api-endpoints)
4. [Data Structures](#data-structures)
5. [Complete Workflow](#complete-workflow)
6. [Error Handling](#error-handling)
7. [Important Notes](#important-notes)
8. [Environment Setup](#environment-setup)

---

## System Overview

This backend analyzes Massachusetts lease agreements for legal violations, risky terms, and favorable clauses using:
- **RAG System**: Combines Snowflake vector search with Gemini AI
- **PII Redaction**: Automatically redacts personally identifiable information
- **PDF Coordinate Extraction**: Generates precise highlights for react-pdf-highlighter
- **Async Processing**: Long-running analysis runs in background with progress tracking

### Key Features
- ✅ Single-stage analysis (no metadata form required)
- ✅ Real-time progress tracking via polling
- ✅ PDF coordinates in PDF.js/react-pdf-highlighter format
- ✅ Color-coded highlights (red=illegal, orange=high risk, yellow=medium, green=favorable)
- ✅ Chat interface for legal questions
- ✅ Automatic PII protection

---

## Quick Start

### 1. Start the Server
```bash
cd app
python server.py
```

Server runs on: `http://localhost:8000`

### 2. Basic Workflow
```javascript
// 1. Upload PDF
const formData = new FormData();
formData.append('file', pdfFile);
const uploadRes = await fetch('http://localhost:8000/upload', {
  method: 'POST',
  body: formData
});
const { file_id } = await uploadRes.json();

// 2. Start Analysis
await fetch('http://localhost:8000/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ file_id })
});

// 3. Poll Status (every 1 second)
const checkStatus = async () => {
  const res = await fetch(`http://localhost:8000/status/${file_id}`);
  const { status, progress } = await res.json();
  return { status, progress };
};

// 4. Get Results (when status === 'completed')
const results = await fetch(`http://localhost:8000/document/${file_id}`);
const analysisData = await results.json();
```

---

## API Endpoints

### 1. Health Check

**`GET /`**

Check if API is running.

**Response:**
```json
{
  "status": "ok",
  "service": "Massachusetts Lease Analyzer API",
  "version": "2.0.0",
  "architecture": "modular"
}
```

---

### 2. Upload Document

**`POST /upload`**

Upload a PDF lease document for analysis. PII is automatically redacted.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` (PDF file)

**Response:**
```json
{
  "file_id": "abc-123-def-456",
  "filename": "sample-lease.pdf",
  "size": 143438,
  "upload_time": "2025-11-08T15:51:18.923150",
  "pii_redacted": {
    "address": 3,
    "person_name": 13,
    "organization": 36
  },
  "message": "File uploaded and PII redacted successfully"
}
```

**Important:**
- Only PDF files accepted
- Returns immediately after upload and PII redaction
- Save the `file_id` for all subsequent requests

---

### 3. Start Analysis

**`POST /analyze`**

Start analyzing the uploaded document. Runs in background.

**Request:**
```json
{
  "file_id": "abc-123-def-456"
}
```

**Response:**
```json
{
  "file_id": "abc-123-def-456",
  "status": "processing",
  "message": "Analysis started. Use GET /status/{file_id} to check progress."
}
```

**Analysis Duration:** 3-5 minutes for a 6-page document (varies with length)

**Gemini API Calls:** ~4 calls (1 per document chunk)

---

### 4. Check Analysis Status

**`GET /status/{file_id}`**

Poll this endpoint to track analysis progress. **Poll every 1 second.**

**Response:**
```json
{
  "file_id": "abc-123-def-456",
  "status": "processing",
  "progress": 65,
  "message": "Analyzing chunk 3/4...",
  "filename": "sample-lease.pdf"
}
```

**Status Values:**
- `"uploaded"` - File uploaded, not yet analyzed
- `"processing"` - Analysis in progress
- `"completed"` - Analysis complete, results ready
- `"failed"` - Analysis failed (check `error` field)

**Progress:** Integer 0-100

**Typical Messages:**
- "Initializing analyzer..." (10%)
- "Loading document text..." (20%)
- "Chunking document..." (30%)
- "Analyzing chunk 1/4..." (40-80%)
- "Consolidating findings..." (85%)
- "Analysis complete" (100%)

---

### 5. Get Analysis Results

**`GET /document/{file_id}`**

Retrieve complete analysis results. **Only call when status === "completed"**.

**Response Structure:**
```json
{
  "file_id": "abc-123-def-456",
  "filename": "sample-lease.pdf",
  "uploaded_at": "2025-11-08T15:51:18.923150",
  "analyzed_at": "2025-11-08T15:55:42.128456",
  "status": "completed",
  "analysis": {
    "documentId": "abc-123-def-456",
    "pdfUrl": "/uploads/abc-123-def-456.pdf",
    "documentMetadata": { /* See Data Structures below */ },
    "deidentificationSummary": { /* PII redaction summary */ },
    "keyDetailsDetected": { /* Detected lease details */ },
    "analysisSummary": { /* Risk summary */ },
    "highlights": [ /* Array of highlights with coordinates */ ],
    "document_info": { /* Additional metadata */ }
  }
}
```

**If analysis not complete:**
```json
{
  "file_id": "abc-123-def-456",
  "status": "processing",
  "message": "Analysis not complete yet. Check /status/{file_id}",
  "progress": 65
}
```

---

### 6. List All Documents

**`GET /documents`**

List all uploaded documents (newest first).

**Response:**
```json
{
  "total": 5,
  "documents": [
    {
      "file_id": "abc-123",
      "filename": "lease1.pdf",
      "uploaded_at": "2025-11-08T15:51:18.923150",
      "status": "completed",
      "size": 143438
    },
    {
      "file_id": "def-456",
      "filename": "lease2.pdf",
      "uploaded_at": "2025-11-08T14:20:10.123456",
      "status": "processing",
      "size": 256789
    }
  ]
}
```

---

### 7. Delete Document

**`DELETE /document/{file_id}`**

Delete a document and its analysis.

**Response:**
```json
{
  "message": "Document deleted successfully",
  "file_id": "abc-123-def-456"
}
```

**Note:** Deletes both the PDF file and all associated data.

---

### 8. Chat with AI

**`POST /chat`**

Ask questions about Massachusetts housing laws. Optionally provide document context.

**Request:**
```json
{
  "message": "What are the rules about security deposits in MA?",
  "file_id": "abc-123-def-456"  // Optional: adds document context
}
```

**Response:**
```json
{
  "answer": "In Massachusetts, security deposits are regulated under M.G.L. c. 186 §15B...",
  "sources": [
    {
      "chapter": "186",
      "section": "15B",
      "relevance": "0.92"
    },
    {
      "chapter": "186",
      "section": "15C",
      "relevance": "0.85"
    }
  ],
  "context": "In the context of the analyzed lease 'sample-lease.pdf'"
}
```

**Use Cases:**
- General legal questions (without `file_id`)
- Document-specific questions (with `file_id`)
- Clarification on violations found

---

## Data Structures

### Analysis Response (Full Structure)

```typescript
interface AnalysisResponse {
  file_id: string;
  filename: string;
  uploaded_at: string;      // ISO 8601 timestamp
  analyzed_at: string;       // ISO 8601 timestamp
  status: "completed";
  analysis: {
    documentId: string;
    pdfUrl: string;          // Relative path to PDF
    
    documentMetadata: {
      fileName: string;
      documentType: "Lease Agreement";
      uploadDate: string;    // YYYY-MM-DD
      fileSize: string;      // e.g., "140 KB"
      pageCount: number;
      parties: {
        landlord: string;    // "See document" if not extracted
        tenant: string;
        property: string;
      };
      leaseDetails: {
        leaseType: string;
        propertyAddress: string;
        leaseTerm: string;
        monthlyRent: string;
        securityDeposit: string;
        specialClauses: string[];
      };
    };
    
    deidentificationSummary: {
      redactedEntities: {
        address: number;     // Count of redacted addresses
        person_name: number; // Count of redacted names
        organization: number;
      };
      encryptionStatus: "enabled" | "disabled";
      privacyNote: string;
    };
    
    keyDetailsDetected: {
      parties: string[];
      propertyInfo: string;
      rentAmount: string;
      leaseTerm: string;
      securityDeposit: string;
      startDate: string;
      endDate: string;
    };
    
    analysisSummary: {
      status: "completed";
      overallRisk: "Low" | "Medium" | "High" | "Critical";
      issuesFound: number;
      estimatedRecovery: string;  // e.g., "$3,400"
      topIssues: string[];
      highlightCounts: {
        illegal: number;      // Red highlights
        highRisk: number;     // Orange highlights
        mediumRisk: number;   // Yellow highlights
        favorable: number;    // Green highlights
      };
    };
    
    highlights: Highlight[];  // See Highlight structure below
    
    document_info: {
      total_chunks: number;
      analysis_method: "RAG with Snowflake + Gemini";
    };
  };
}
```

---

### Highlight Structure (react-pdf-highlighter Compatible)

```typescript
interface Highlight {
  id: string;                    // e.g., "hl-001"
  pageNumber: number;            // 1-indexed
  color: "red" | "orange" | "yellow" | "green";
  priority: "critical" | "high" | "medium" | "low";
  category: string;              // e.g., "Chapter 186, Section 15"
  text: string;                  // Exact text from PDF
  statute: string;               // Legal citation
  explanation: string;           // Why this is problematic/favorable
  damages_estimate: number | null;  // Dollar amount (for illegal clauses)
  
  position: {
    boundingRect: {
      x1: number;          // Left edge (points)
      y1: number;          // Bottom edge (from page bottom!)
      x2: number;          // Right edge (points)
      y2: number;          // Top edge (from page bottom!)
      width: number;       // x2 - x1
      height: number;      // y2 - y1
      pageNumber: number;  // Same as parent
    };
    rects: Array<{       // Individual lines for multi-line text
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      width: number;
      height: number;
      pageNumber: number;
    }>;
    pageHeight: number;  // Page height in points (e.g., 792)
    pageWidth: number;   // Page width in points (e.g., 612)
  };
}
```

**CRITICAL: Coordinate System**
- **Origin**: Bottom-left corner (PDF.js standard)
- **Y-axis**: Increases upward (0 = bottom, 792 = top for US Letter)
- **Y2 > Y1**: Always true (y2 is top, y1 is bottom)
- **Units**: Points (1/72 inch)
- **Compatible with**: react-pdf-highlighter, PDF.js

**Color Meanings:**
- 🔴 **Red (`"red"`)**: Illegal clause - violates MA law
- 🟠 **Orange (`"orange"`)**: High risk term
- 🟡 **Yellow (`"yellow"`)**: Medium risk term
- 🟢 **Green (`"green"`)**: Favorable tenant clause

---

## Complete Workflow

### Typical User Flow

```
1. User uploads PDF
   ↓
   POST /upload → Returns file_id
   
2. Frontend automatically starts analysis
   ↓
   POST /analyze with file_id
   
3. Frontend polls status every 1 second
   ↓
   GET /status/{file_id} until status === "completed"
   ↓
   Show progress bar with message updates
   
4. Fetch and display results
   ↓
   GET /document/{file_id}
   ↓
   Parse highlights and render with react-pdf-highlighter
   
5. (Optional) User asks questions
   ↓
   POST /chat with message and file_id
```

### Progress Bar Implementation

```javascript
async function pollStatus(fileId) {
  const poll = setInterval(async () => {
    const res = await fetch(`/status/${fileId}`);
    const { status, progress, message } = await res.json();
    
    // Update UI
    updateProgressBar(progress);
    updateStatusMessage(message);
    
    if (status === 'completed') {
      clearInterval(poll);
      await loadResults(fileId);
    } else if (status === 'failed') {
      clearInterval(poll);
      showError(message);
    }
  }, 1000);  // Poll every 1 second
}
```

---

## Error Handling

### HTTP Status Codes

- **200**: Success
- **400**: Bad request (e.g., non-PDF file)
- **404**: Document not found
- **500**: Server error

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Errors

**Upload Errors:**
- "Only PDF files are allowed" - File is not a PDF
- "Upload failed: [reason]" - Server error during upload

**Analysis Errors:**
- "Document not found" - Invalid file_id
- "Analysis failed: [reason]" - Error during analysis
- Status will be set to `"failed"` with error message

**Chat Errors:**
- "Chat failed: [reason]" - Error querying RAG system

### Error Handling Example

```javascript
try {
  const res = await fetch('/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id })
  });
  
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail);
  }
  
  const data = await res.json();
  // Handle success
  
} catch (error) {
  console.error('Analysis failed:', error.message);
  // Show user-friendly error message
}
```

---

## Important Notes

### 1. Coordinate System for Highlights

**CRITICAL FOR RENDERING:**

The `position` coordinates in highlights are in **PDF.js format** (bottom-left origin), NOT standard image coordinates (top-left origin).

```javascript
// ✅ CORRECT: Use coordinates directly with react-pdf-highlighter
<PdfHighlighter
  highlights={analysis.highlights.map(h => ({
    id: h.id,
    position: h.position,  // Use as-is!
    comment: { text: h.explanation }
  }))}
/>

// ❌ WRONG: Do NOT transform coordinates
// They are already in the correct format for PDF.js
```

**Verification:**
- `position.boundingRect.y2` should always be > `y1`
- For top of page: y-values near `pageHeight` (e.g., 792)
- For bottom of page: y-values near 0

### 2. Polling Best Practices

- **Interval**: 1 second (balance between responsiveness and server load)
- **Timeout**: Set a max timeout (5-10 minutes) in case of failure
- **Stop conditions**: `status === "completed"` OR `status === "failed"`
- **User feedback**: Always show progress % and current message

### 3. PII Protection

All uploaded documents are automatically processed for PII:
- Names → `[NAME_REDACTED]`
- Addresses → `[ADDRESS_REDACTED]`
- Organizations → `[ORG_REDACTED]`

Original text is encrypted and stored separately. Analysis uses redacted text.

### 4. File Storage

Files are stored in:
- Original PDF: `app/uploads/{file_id}.pdf`
- Redacted text: `app/uploads/{file_id}_redacted.txt`
- Metadata: `app/data/documents.json`

### 5. Resource Requirements

**Typical Analysis:**
- Time: 3-5 minutes (6-page document)
- Gemini API calls: ~4 (1 per chunk)
- Document is chunked into ~4000 token segments

**Snowflake Database:**
- Contains Massachusetts General Laws (Chapters 93A, 186, etc.)
- Vector embeddings for semantic search
- Required for RAG to function

---

## Environment Setup

### Required Environment Variables

Create `.env` file in project root:

```bash
# Snowflake Configuration
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema

# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Optional
ENCRYPTION_KEY=your_encryption_key_for_pii
```

### Python Dependencies

Install via `requirements.txt`:

```bash
pip install -r requirements.txt
```

Key packages:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `snowflake-connector-python` - Database connection
- `google-generativeai` - Gemini API
- `PyPDF2` - PDF text extraction
- `pdfplumber` - PDF coordinate extraction
- `spacy` - NLP for PII detection
- `presidio-analyzer` - PII redaction

### Database Setup

Snowflake table must contain:
```sql
CREATE TABLE legal_documents (
  id NUMBER,
  chapter VARCHAR,
  section VARCHAR,
  text VARCHAR,
  embedding VECTOR(FLOAT, 1024)  -- Gemini embeddings
);
```

### Starting the Server

```bash
cd app
python server.py
```

Server will start on `http://localhost:8000`

**API Documentation:** `http://localhost:8000/docs` (Swagger UI)

---

## Integration Checklist

### Frontend Requirements

- [ ] File upload component (accepts PDF only)
- [ ] Progress bar with status messages
- [ ] Results display with color-coded highlights
- [ ] PDF viewer (recommend `react-pdf-highlighter`)
- [ ] Chat interface (optional)
- [ ] Error handling for all API calls
- [ ] Loading states during analysis
- [ ] Responsive design for mobile/tablet

### Testing Checklist

- [ ] Upload valid PDF → receives file_id
- [ ] Upload non-PDF → receives 400 error
- [ ] Start analysis → status changes to "processing"
- [ ] Poll status → progress increases 0-100%
- [ ] Get results when complete → receives full analysis JSON
- [ ] Highlights render correctly on PDF
- [ ] Y-axis coordinates verified (y2 > y1)
- [ ] Chat functionality works (with and without file_id)
- [ ] Error messages display properly
- [ ] Can delete documents

### Example Test Flow

```bash
# 1. Upload
curl -X POST http://localhost:8000/upload \
  -F "file=@sample-lease.pdf"

# 2. Start analysis (use file_id from step 1)
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"file_id":"abc-123"}'

# 3. Check status
curl http://localhost:8000/status/abc-123

# 4. Get results (when complete)
curl http://localhost:8000/document/abc-123

# 5. Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is Chapter 186?","file_id":"abc-123"}'
```

---

## Support & Troubleshooting

### Common Issues

**"No module named 'api'"**
- Fix: The API file is named `api_v2.py`, update imports accordingly

**"Snowflake connection failed"**
- Check `.env` file has correct credentials
- Verify Snowflake warehouse is running

**"Gemini API rate limit"**
- Analysis uses ~4 API calls per document
- Check your Gemini API quota

**Coordinates appear inverted**
- Verify you're not transforming the coordinates
- They are already in PDF.js format (bottom-left origin)

### Debug Mode

Check server logs for detailed error messages:
```bash
python server.py 2>&1 | tee server.log
```

---

## API Versioning

**Current Version:** 2.0.0

**Changelog:**
- **v2.0.0**: Single-stage analysis, react-pdf-highlighter coordinates, simplified workflow
- **v1.0.0**: Two-stage analysis with metadata form

---

**Last Updated:** November 8, 2025  
**Backend Status:** ✅ Production Ready  
**Frontend Integration:** Ready for implementation

