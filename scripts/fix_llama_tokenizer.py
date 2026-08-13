#!/usr/bin/env python3
"""
Script to fix the LLaMA tokenizer issue by creating a backup and trying alternative approaches
"""
import json
import shutil
from pathlib import Path

def backup_and_fix_tokenizer():
    """Backup the corrupted tokenizer and try to fix it"""
    model_dir = Path("llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1")
    tokenizer_json = model_dir / "tokenizer.json"
    
    if not tokenizer_json.exists():
        print("❌ tokenizer.json not found")
        return False
    
    # Create backup
    backup_file = model_dir / "tokenizer.json.backup"
    print(f"📋 Creating backup: {backup_file}")
    shutil.copy2(tokenizer_json, backup_file)
    
    # Try to read and fix the JSON
    try:
        print("🔍 Reading tokenizer.json...")
        with open(tokenizer_json, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📊 File size: {len(content)} characters")
        
        # Try to parse JSON
        try:
            data = json.loads(content)
            print("✅ JSON is valid, no fix needed")
            return True
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error at line {e.lineno}, column {e.colno}")
            
            # Try to fix by truncating at the error line
            lines = content.split('\n')
            if e.lineno <= len(lines):
                print(f"🔧 Attempting to fix by truncating at line {e.lineno}")
                fixed_lines = lines[:e.lineno-1]
                fixed_content = '\n'.join(fixed_lines)
                
                # Try to parse the truncated version
                try:
                    json.loads(fixed_content)
                    print("✅ Truncated version is valid JSON")
                    
                    # Write the fixed version
                    with open(tokenizer_json, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)
                    print("💾 Fixed tokenizer.json saved")
                    return True
                except json.JSONDecodeError:
                    print("❌ Truncated version still invalid")
            
            return False
            
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def try_alternative_loading():
    """Try loading the model with different approaches"""
    try:
        from transformers import AutoTokenizer, AutoModelForTokenClassification
        
        model_dir = "llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1"
        
        print("🔄 Trying to load with local_files_only=True...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir, 
            local_files_only=True,
            use_fast=False
        )
        model = AutoModelForTokenClassification.from_pretrained(
            model_dir,
            local_files_only=True
        )
        print("✅ Successfully loaded with local_files_only=True")
        return True
        
    except Exception as e:
        print(f"❌ local_files_only failed: {e}")
        return False

def main():
    print("🔧 LLaMA Tokenizer Fix Script")
    print("=" * 40)
    
    # Try to fix the tokenizer file
    if backup_and_fix_tokenizer():
        print("\n🔄 Testing fixed tokenizer...")
        if try_alternative_loading():
            print("✅ Tokenizer fix successful!")
        else:
            print("❌ Tokenizer still has issues")
    else:
        print("❌ Could not fix tokenizer file")

if __name__ == "__main__":
    main()
