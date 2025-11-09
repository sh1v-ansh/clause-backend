"""Test voice chat endpoint"""
import sys
import os
import tempfile
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from api_v2 import app

client = TestClient(app)

# Create a minimal valid WebM file for testing
# WebM header: 0x1A 0x45 0xDF 0xA3
webm_header = b'\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f\x42\x86\x81\x01'
test_audio = webm_header + b'\x00' * 500  # Add some data

print("[TEST] Testing voice chat endpoint...")
print(f"[TEST] Test audio size: {len(test_audio)} bytes")

# Create temporary file
with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as f:
    f.write(test_audio)
    test_file = f.name

try:
    # Test the endpoint
    with open(test_file, 'rb') as audio_file:
        response = client.post(
            '/chat/voice',
            files={'audio': ('test.webm', audio_file, 'audio/webm')},
            data={'file_id': 'test'}
        )
    
    print(f"\n[TEST] Status Code: {response.status_code}")
    print(f"[TEST] Content-Type: {response.headers.get('content-type')}")
    print(f"[TEST] Response Size: {len(response.content)} bytes")
    print(f"[TEST] X-Original-Text: {response.headers.get('x-original-text', 'N/A')}")
    print(f"[TEST] X-Response-Text: {response.headers.get('x-response-text', 'N/A')}")
    
    if response.status_code == 200:
        print("\n[OK] Voice chat endpoint is working!")
    else:
        print(f"\n[ERROR] Endpoint returned {response.status_code}")
        print(f"[ERROR] Response: {response.text[:500]}")
        
except Exception as e:
    print(f"\n[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
finally:
    if os.path.exists(test_file):
        os.unlink(test_file)

