"""
FastAPI backend for Massachusetts Lease Analyzer (Refactored)
Clean, modular architecture with separate routes and services
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import upload, analysis, documents, chat

# Initialize FastAPI app
app = FastAPI(
    title="Massachusetts Lease Analyzer API",
    description="AI-powered lease analysis using RAG and MA housing laws",
    version="2.0.0"
)

# CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, tags=["Upload"])
app.include_router(analysis.router, tags=["Analysis"])
app.include_router(documents.router, tags=["Documents"])
app.include_router(chat.router, tags=["Chat"])


# Health check endpoint
@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Massachusetts Lease Analyzer API",
        "version": "2.0.0",
        "architecture": "modular"
    }

@app.post("/analyze-listing")
async def analyze_listing(listing_data: dict):
    # Hardcoded demo response
    return {
        "listing_id": listing_data["listing_id"],
        "risk_score": 75,
        "risk_level": "high",
        "violations": [
            {
                "title": "Cash-only cleaning fee",
                "description": "Requiring cash payment violates Airbnb Terms of Service",
                "law": "Airbnb ToS Section 5.3",
                "severity": "high"
            },
            {
                "title": "Non-refundable security deposit",
                "description": "MA law requires security deposits to be refundable",
                "law": "M.G.L. c. 186 § 15B",
                "severity": "high"
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

