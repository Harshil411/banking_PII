#!/usr/bin/env python3
"""
Test BERT model loading and inference
"""
import sys
from pathlib import Path

def test_bert_model():
    """Test BERT model loading and inference"""
    try:
        from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
        
        model_dir = Path("bert-base-multilingual-cased_100k_v1")
        
        print("🔄 Loading BERT tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        print("✅ Tokenizer loaded")
        
        print("🔄 Loading BERT model...")
        model = AutoModelForTokenClassification.from_pretrained(model_dir)
        print("✅ Model loaded")
        
        print("🔄 Creating pipeline...")
        pipe = pipeline(
            task="token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
            device=-1  # CPU
        )
        print("✅ Pipeline created")
        
        print("🔄 Testing inference...")
        text = "My name is John Doe"
        results = pipe(text)
        print(f"📊 Results: {results}")
        
        # Test result processing
        for i, r in enumerate(results):
            print(f"Result {i}: {r}")
            print(f"  Keys: {list(r.keys())}")
            print(f"  Values: {list(r.values())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bert_model()
    sys.exit(0 if success else 1)
