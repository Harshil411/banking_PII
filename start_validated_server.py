#!/usr/bin/env python3
"""
Start the validated PII detection server
"""

import subprocess
import sys
import time
import requests
from pathlib import Path

def check_server_running():
    """Check if server is already running"""
    try:
        response = requests.get("http://localhost:8000/api/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def start_server():
    """Start the validated server"""
    print("🚀 Starting Validated PII Detection Server")
    print("=" * 50)
    
    # Check if server is already running
    if check_server_running():
        print("✅ Server is already running on http://localhost:8000")
        print("🌐 You can now test the frontend with validated detection!")
        return True
    
    print("🔄 Starting server...")
    
    try:
        # Start the server
        process = subprocess.Popen([
            sys.executable, "-m", "uvicorn", 
            "backend.validated_enhanced_main:app", 
            "--reload", 
            "--host", "0.0.0.0", 
            "--port", "8000"
        ], cwd=Path.cwd())
        
        print("⏳ Waiting for server to start...")
        
        # Wait for server to start
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            if check_server_running():
                print("✅ Server started successfully!")
                print("🌐 Server URL: http://localhost:8000")
                print("📊 Health check: http://localhost:8000/api/health")
                print("🔍 Validated detection: http://localhost:8000/api/validated/detect")
                print()
                print("🎯 Now you can:")
                print("1. Open your frontend in the browser")
                print("2. Check the 'Use Validated Detection' checkbox")
                print("3. Test with sample data to see false positive filtering!")
                print()
                print("Press Ctrl+C to stop the server")
                
                try:
                    process.wait()
                except KeyboardInterrupt:
                    print("\n🛑 Stopping server...")
                    process.terminate()
                    process.wait()
                    print("✅ Server stopped")
                
                return True
        
        print("❌ Server failed to start within 30 seconds")
        process.terminate()
        return False
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

def test_validated_detection():
    """Test the validated detection with problematic data"""
    print("\n🧪 Testing Validated Detection")
    print("=" * 30)
    
    # Test with the problematic data you mentioned
    test_data = {
        "text": "Some data: 1234 - 5678 - and 9012, 9876543210, ABCDE1234F",
        "use_regex": True,
        "use_contextual": True,
        "use_ml": False,
        "min_confidence": 0.5
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/api/validated/detect",
            json=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Test successful!")
            print(f"📊 Valid entities: {len(data.get('entities', []))}")
            print(f"❌ Filtered entities: {len(data.get('filtered_entities', []))}")
            
            if data.get('filtered_entities'):
                print("\n🔍 Filtered false positives:")
                for entity in data['filtered_entities']:
                    print(f"  - {entity['entity_group']}: '{entity['word']}' - {entity['filter_reason']}")
            
            if data.get('entities'):
                print("\n✅ Valid detections:")
                for entity in data['entities']:
                    print(f"  - {entity['entity_group']}: '{entity['word']}'")
        else:
            print(f"❌ Test failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    if start_server():
        test_validated_detection()
    else:
        print("❌ Failed to start server")
        sys.exit(1)
