"""Verify voice chat endpoint is registered and accessible"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from api_v2 import app
    print("[OK] Successfully imported app")
    
    # Check if voice_chat route is registered
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append((route.path, list(route.methods)))
    
    voice_routes = [r for r in routes if 'voice' in r[0] or 'chat' in r[0]]
    
    print("\n[INFO] Registered Voice/Chat Routes:")
    for path, methods in sorted(voice_routes):
        print(f"  {methods} {path}")
    
    # Check specifically for /chat/voice
    voice_route = [r for r in routes if r[0] == '/chat/voice']
    if voice_route:
        print(f"\n[OK] Voice chat endpoint found: {voice_route[0][1]} {voice_route[0][0]}")
    else:
        print("\n[ERROR] Voice chat endpoint NOT found!")
        print("   Make sure voice_chat router is imported and registered in api_v2.py")
        
    # Test import
    try:
        from routes import voice_chat
        print("[OK] voice_chat module imported successfully")
    except ImportError as e:
        print(f"[ERROR] Failed to import voice_chat: {e}")
        
except Exception as e:
    print(f"[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()

