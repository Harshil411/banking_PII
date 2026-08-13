#!/usr/bin/env python3
"""
Test script to isolate tokenizer loading issues
"""
import sys
from pathlib import Path

def test_tokenizer_loading():
    """Test different tokenizer loading approaches"""
    try:
        from transformers import AutoTokenizer
        print("✅ Transformers imported successfully")
    except Exception as e:
        print(f"❌ Failed to import transformers: {e}")
        return False
    
    model_dir = Path("llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1")
    
    if not model_dir.exists():
        print(f"❌ Model directory not found: {model_dir}")
        return False
    
    print(f"📁 Testing tokenizer loading from: {model_dir}")
    
    # Test 1: Basic loading
    try:
        print("🔄 Test 1: Basic loading...")
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        print("✅ Basic loading successful")
        return True
    except Exception as e:
        print(f"❌ Basic loading failed: {e}")
    
    # Test 2: With use_fast=False
    try:
        print("🔄 Test 2: use_fast=False...")
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), use_fast=False)
        print("✅ use_fast=False successful")
        return True
    except Exception as e:
        print(f"❌ use_fast=False failed: {e}")
    
    # Test 3: With trust_remote_code=True
    try:
        print("🔄 Test 3: trust_remote_code=True...")
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        print("✅ trust_remote_code=True successful")
        return True
    except Exception as e:
        print(f"❌ trust_remote_code=True failed: {e}")
    
    # Test 4: Check if it's a tokenizers library issue
    try:
        print("🔄 Test 4: Testing tokenizers library...")
        from tokenizers import Tokenizer
        tokenizer_file = model_dir / "tokenizer.json"
        if tokenizer_file.exists():
            tokenizer = Tokenizer.from_file(str(tokenizer_file))
            print("✅ Direct tokenizers library loading successful")
            return True
        else:
            print("❌ tokenizer.json not found")
    except Exception as e:
        print(f"❌ Direct tokenizers library failed: {e}")
    
    print("❌ All tokenizer loading methods failed")
    return False

if __name__ == "__main__":
    success = test_tokenizer_loading()
    sys.exit(0 if success else 1)
