#!/usr/bin/env python3
"""
Script to diagnose and potentially fix tokenizer issues
"""
import json
from pathlib import Path

def check_tokenizer_files(model_dir):
    """Check the integrity of tokenizer files"""
    model_path = Path(model_dir)
    
    print(f"🔍 Checking tokenizer files in: {model_path}")
    
    # Check tokenizer.json
    tokenizer_json = model_path / "tokenizer.json"
    if tokenizer_json.exists():
        print(f"📄 Found tokenizer.json ({tokenizer_json.stat().st_size} bytes)")
        try:
            with open(tokenizer_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print("✅ tokenizer.json is valid JSON")
            return True
        except json.JSONDecodeError as e:
            print(f"❌ tokenizer.json is corrupted: {e}")
            print(f"   Error at line {e.lineno}, column {e.colno}")
            return False
        except Exception as e:
            print(f"❌ Error reading tokenizer.json: {e}")
            return False
    else:
        print("❌ tokenizer.json not found")
        return False

def check_vocab_file(model_dir):
    """Check if vocab.txt exists and is readable"""
    model_path = Path(model_dir)
    vocab_file = model_path / "vocab.txt"
    
    if vocab_file.exists():
        print(f"📄 Found vocab.txt ({vocab_file.stat().st_size} bytes)")
        try:
            with open(vocab_file, 'r', encoding='utf-8') as f:
                lines = vocab_file.read_text(encoding='utf-8').strip().split('\n')
            print(f"✅ vocab.txt is readable ({len(lines)} lines)")
            return True
        except Exception as e:
            print(f"❌ Error reading vocab.txt: {e}")
            return False
    else:
        print("❌ vocab.txt not found")
        return False

def main():
    """Main function to check both models"""
    models = [
        "bert-base-multilingual-cased_100k_v1",
        "llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1"
    ]
    
    print("🔧 Tokenizer File Integrity Checker")
    print("=" * 50)
    
    for model in models:
        print(f"\n📁 Checking {model}:")
        print("-" * 30)
        
        tokenizer_ok = check_tokenizer_files(model)
        vocab_ok = check_vocab_file(model)
        
        if not tokenizer_ok and vocab_ok:
            print("💡 Suggestion: Use vocab.txt-based tokenizer loading")
        elif not tokenizer_ok and not vocab_ok:
            print("⚠️  Warning: Both tokenizer files have issues")
        else:
            print("✅ All tokenizer files look good")

if __name__ == "__main__":
    main()
