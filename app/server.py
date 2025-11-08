"""
Main server file that combines API and static file serving
"""
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api_v2 import app
import os

# Mount static files directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Serve index.html at root
@app.get("/app", response_class=FileResponse)
async def serve_app():
    """Serve the frontend application"""
    return os.path.join(static_dir, "index.html")

if __name__ == "__main__":
    print("="*80)
    print("🏠 MASSACHUSETTS LEASE ANALYZER")
    print("="*80)
    print("\n📡 Starting server...")
    print("   - API: http://localhost:8000")
    print("   - Web App: http://localhost:8000/app")
    print("   - API Docs: http://localhost:8000/docs")
    print("\nPress CTRL+C to stop\n")
    print("="*80 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

