# API Quick Reference

## Base URL
```
http://localhost:8000
```

## Essential Endpoints

### 1️⃣ Upload PDF
```bash
POST /upload
Content-Type: multipart/form-data

# Returns:
{
  "file_id": "abc-123",
  "filename": "lease.pdf",
  "pii_redacted": {...}
}
```

### 2️⃣ Start Analysis
```bash
POST /analyze
Content-Type: application/json
Body: {"file_id": "abc-123"}

# Returns:
{
  "file_id": "abc-123",
  "status": "processing",
  "message": "Analysis started..."
}
```

### 3️⃣ Check Status (Poll every 1s)
```bash
GET /status/{file_id}

# Returns:
{
  "status": "processing",  // or "completed" or "failed"
  "progress": 65,          // 0-100
  "message": "Analyzing chunk 3/4..."
}
```

### 4️⃣ Get Results
```bash
GET /document/{file_id}

# Returns: Complete analysis JSON with highlights
```

---

## Highlight Coordinate System

**CRITICAL:** Coordinates are in **PDF.js format** (bottom-left origin)

```typescript
position: {
  boundingRect: {
    x1: number,  // Left
    y1: number,  // Bottom (from page bottom!)
    x2: number,  // Right
    y2: number,  // Top (from page bottom!)
    width: number,
    height: number
  },
  pageHeight: 792,  // US Letter
  pageWidth: 612
}
```

**Always true:** `y2 > y1`

**Compatible with:** `react-pdf-highlighter` (use directly, no transformation!)

---

## Color Codes

| Color | Meaning | Priority |
|-------|---------|----------|
| 🔴 Red | Illegal clause | Critical |
| 🟠 Orange | High risk term | High |
| 🟡 Yellow | Medium risk | Medium |
| 🟢 Green | Favorable clause | Low |

---

## Typical Flow

```javascript
// 1. Upload
const upload = await fetch('/upload', {
  method: 'POST',
  body: formData
});
const { file_id } = await upload.json();

// 2. Analyze
await fetch('/analyze', {
  method: 'POST',
  body: JSON.stringify({ file_id })
});

// 3. Poll (every 1 second)
const interval = setInterval(async () => {
  const res = await fetch(`/status/${file_id}`);
  const { status, progress } = await res.json();
  
  if (status === 'completed') {
    clearInterval(interval);
    loadResults(file_id);
  }
}, 1000);

// 4. Results
const results = await fetch(`/document/${file_id}`);
const data = await results.json();
const highlights = data.analysis.highlights;
```

---

## Analysis Time
- **6-page document:** ~3-5 minutes
- **Gemini API calls:** ~4 (1 per chunk)

---

## Full Documentation
See `BACKEND_API_DOCUMENTATION.md` for complete details.

