#!/usr/bin/env python3
"""
Enhanced PII Detection System
Combines ML models with regex-based pattern matching for comprehensive PII detection
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

class EnhancedPIIDetector:
    def __init__(self, bert_model_path: str, llama_model_path: str, schema_path: str):
        self.bert_model_path = Path(bert_model_path)
        self.llama_model_path = Path(llama_model_path)
        self.schema_path = Path(schema_path)
        
        # Load data schema
        with open(self.schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)
        
        # Initialize models
        self.device = 0 if torch.cuda.is_available() else -1
        self.bert_pipe = None
        self.llama_pipe = None
        
        # Load models
        self._load_models()
        
        # Compile regex patterns for enhanced detection
        self._compile_regex_patterns()
    
    def _load_models(self):
        """Load BERT and LLaMA models"""
        try:
            self.bert_pipe = self._load_token_classifier(self.bert_model_path)
            print("✅ BERT model loaded successfully")
        except Exception as e:
            print(f"❌ Failed to load BERT model: {e}")
            self.bert_pipe = None
        
        try:
            self.llama_pipe = self._load_token_classifier(self.llama_model_path)
            print("✅ LLaMA model loaded successfully")
        except Exception as e:
            print(f"❌ Failed to load LLaMA model: {e}")
            self.llama_pipe = None
    
    def _load_token_classifier(self, model_dir: Path):
        """Load token classification model with error handling"""
        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")
        
        # Special handling for LLaMA model
        if "llama" in str(model_dir).lower():
            try:
                model = AutoModelForTokenClassification.from_pretrained(model_dir)
                tokenizer = AutoTokenizer.from_pretrained(
                    "bert-base-multilingual-cased",
                    use_fast=True
                )
                return pipeline(
                    task="token-classification",
                    model=model,
                    tokenizer=tokenizer,
                    aggregation_strategy="simple",
                    device=self.device,
                )
            except Exception as e:
                print(f"❌ LLaMA special loading failed: {e}")
        
        # Try different loading strategies
        loading_strategies = [
            {"trust_remote_code": True, "use_fast": False},
            {"trust_remote_code": False, "use_fast": False},
            {"trust_remote_code": False, "use_fast": True},
            {"local_files_only": True, "use_fast": False},
        ]
        
        for strategy in loading_strategies:
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_dir, **strategy)
                model = AutoModelForTokenClassification.from_pretrained(
                    model_dir, 
                    trust_remote_code=strategy.get("trust_remote_code", False),
                    local_files_only=strategy.get("local_files_only", False)
                )
                return pipeline(
                    task="token-classification",
                    model=model,
                    tokenizer=tokenizer,
                    aggregation_strategy="simple",
                    device=self.device,
                )
            except Exception as e:
                continue
        
        raise RuntimeError(f"All loading strategies failed for {model_dir}")
    
    def _compile_regex_patterns(self):
        """Compile regex patterns from schema for enhanced detection"""
        self.regex_patterns = {}
        for category, config in self.schema.items():
            try:
                pattern = config['regex']
                # Enhance patterns for better detection
                enhanced_pattern = self._enhance_regex_pattern(category, pattern)
                self.regex_patterns[category] = re.compile(enhanced_pattern, re.IGNORECASE)
            except Exception as e:
                print(f"⚠️  Warning: Could not compile regex for {category}: {e}")
                self.regex_patterns[category] = None
    
    def _enhance_regex_pattern(self, category: str, pattern: str) -> str:
        """Enhance regex patterns for better detection"""
        enhancements = {
            'GIVENNAME': r'\b[A-Z][a-z]{1,20}\b',
            'SURNAME': r'\b[A-Z][a-z]{1,20}\b',
            'FULLNAME': r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\b',
            'TELEPHONENUM': r'(?:\+91[-\\s]?|0)?[6789]\\d{9}',
            'EMAIL': r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+',
            'CITY': r'\\b[A-Za-z\\s]+\\b',
            'BUILDINGNUM': r'\\b\\d{1,4}\\b',
            'STREET': r'\\b[A-Za-z0-9\\s]+(?:Street|Road|Avenue|Lane|Drive|Way|Boulevard|Place)\\b',
            'ZIPCODE': r'\\b\\d{6}\\b',
            'DATE': r'\\b\\d{2}[-/]\\d{2}[-/]\\d{4}\\b',
            'TIME': r'\\b\\d{2}:\\d{2}(?::\\d{2})?\\b',
            'AGE': r'\\b\\d{1,3}\\b',
            'AADHAAR': r'\\b\\d{4}\\s\\d{4}\\s\\d{4}\\b',
            'PAN': r'\\b[A-Z]{3}[PFCHAT][A-Z]\\d{4}[A-Z]\\b',
            'VOTERID': r'\\b[A-Z]{3}\\d{7}\\b',
            'DRIVERLICENSENUM': r'\\b[A-Z]{2}[-\\s]?\\d{2}[-\\s]?\\d{4}[-\\s]?\\d{7}\\b',
            'ACCOUNTNUM': r'\\b\\d{9,18}\\b',
            'IFSC': r'\\b[A-Z]{4}0[A-Z0-9]{6}\\b',
            'CREDITCARDNUM': r'\\b\\d{4}\\s\\d{4}\\s\\d{4}\\s\\d{4}\\b',
            'TRANSACTIONID': r'\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\\b',
            'GENDER': r'\\b(M|F|Male|Female)\\b',
            'PASSPORTNUM': r'\\b[A-Z]\\d{7}\\b'
        }
        
        return enhancements.get(category, pattern)
    
    def detect_with_regex(self, text: str) -> List[Dict]:
        """Detect PII using regex patterns"""
        entities = []
        
        for category, pattern in self.regex_patterns.items():
            if pattern is None:
                continue
                
            for match in pattern.finditer(text):
                entities.append({
                    'entity_group': category,
                    'word': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'score': 0.9,  # High confidence for regex matches
                    'method': 'regex'
                })
        
        return entities
    
    def detect_with_ml(self, text: str, model_type: str = 'bert') -> List[Dict]:
        """Detect PII using ML models"""
        pipe = self.bert_pipe if model_type == 'bert' else self.llama_pipe
        
        if pipe is None:
            return []
        
        try:
            results = pipe(text)
            entities = []
            
            for r in results:
                entities.append({
                    'entity_group': r.get('entity_group', 'UNKNOWN'),
                    'word': r.get('word', ''),
                    'start': int(r.get('start', 0)),
                    'end': int(r.get('end', 0)),
                    'score': float(r.get('score', 0.0)),
                    'method': f'ml_{model_type}'
                })
            
            return entities
        except Exception as e:
            print(f"❌ ML detection error: {e}")
            return []
    
    def detect_comprehensive(self, text: str) -> Dict:
        """Comprehensive PII detection combining multiple methods"""
        results = {
            'text': text,
            'entities': [],
            'summary': {},
            'methods_used': []
        }
        
        # Method 1: Regex-based detection
        regex_entities = self.detect_with_regex(text)
        results['entities'].extend(regex_entities)
        if regex_entities:
            results['methods_used'].append('regex')
        
        # Method 2: BERT model detection
        if self.bert_pipe:
            bert_entities = self.detect_with_ml(text, 'bert')
            results['entities'].extend(bert_entities)
            results['methods_used'].append('bert')
        
        # Method 3: LLaMA model detection
        if self.llama_pipe:
            llama_entities = self.detect_with_ml(text, 'llama')
            results['entities'].extend(llama_entities)
            results['methods_used'].append('llama')
        
        # Merge and deduplicate entities
        results['entities'] = self._merge_entities(results['entities'])
        
        # Generate summary
        results['summary'] = self._generate_summary(results['entities'])
        
        return results
    
    def _merge_entities(self, entities: List[Dict]) -> List[Dict]:
        """Merge overlapping entities and remove duplicates"""
        if not entities:
            return []
        
        # Sort by start position
        entities.sort(key=lambda x: x['start'])
        
        merged = []
        current = entities[0].copy()
        
        for entity in entities[1:]:
            # Check for overlap
            if (entity['start'] < current['end'] and 
                entity['entity_group'] == current['entity_group']):
                # Merge overlapping entities
                current['end'] = max(current['end'], entity['end'])
                current['word'] = entity['word']  # Use the longer match
                current['score'] = max(current['score'], entity['score'])
                if 'method' in entity:
                    current['method'] = f"{current.get('method', '')}+{entity['method']}"
            else:
                merged.append(current)
                current = entity.copy()
        
        merged.append(current)
        return merged
    
    def _generate_summary(self, entities: List[Dict]) -> Dict:
        """Generate summary statistics"""
        summary = {
            'total_entities': len(entities),
            'categories_found': set(),
            'confidence_scores': [],
            'methods_used': set()
        }
        
        for entity in entities:
            summary['categories_found'].add(entity['entity_group'])
            summary['confidence_scores'].append(entity['score'])
            if 'method' in entity:
                summary['methods_used'].add(entity['method'])
        
        summary['categories_found'] = list(summary['categories_found'])
        summary['methods_used'] = list(summary['methods_used'])
        summary['avg_confidence'] = sum(summary['confidence_scores']) / len(summary['confidence_scores']) if summary['confidence_scores'] else 0
        
        return summary
    
    def anonymize_text(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Anonymize detected PII in text"""
        results = self.detect_comprehensive(text)
        entities = results['entities']
        
        if not entities:
            return text
        
        # Sort entities by start position (reverse order for replacement)
        sorted_entities = sorted(entities, key=lambda x: x['start'], reverse=True)
        
        anonymized = text
        for entity in sorted_entities:
            start, end = entity['start'], entity['end']
            anonymized = anonymized[:start] + replacement + anonymized[end:]
        
        return anonymized


def main():
    """Test the enhanced PII detector"""
    # Initialize detector
    detector = EnhancedPIIDetector(
        bert_model_path="bert-base-multilingual-cased_100k_v1",
        llama_model_path="llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1",
        schema_path="data_schema.json"
    )
    
    # Test cases
    test_cases = [
        "My name is Arun Sharma and my email is arun.sharma@hdfc.com",
        "Contact me at +91-9876543210 or visit 123 MG Road, Mumbai 400001",
        "PAN: AAAPA1234A, Aadhaar: 1234 5678 9012, DOB: 15/08/1990",
        "Transaction ID: f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "Passport: K1234567, Driver License: MH-14-2011-0062821",
        "Account: 123456789, IFSC: HDFC0001234, Credit Card: 4111 1111 1111 1111"
    ]
    
    print("🔍 Enhanced PII Detection Test Results")
    print("=" * 50)
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\nTest Case {i}: {test_text}")
        print("-" * 30)
        
        # Detect PII
        results = detector.detect_comprehensive(test_text)
        
        print(f"Entities found: {results['summary']['total_entities']}")
        print(f"Categories: {', '.join(results['summary']['categories_found'])}")
        print(f"Methods used: {', '.join(results['summary']['methods_used'])}")
        print(f"Avg confidence: {results['summary']['avg_confidence']:.3f}")
        
        # Show individual entities
        for entity in results['entities']:
            print(f"  - {entity['entity_group']}: '{entity['word']}' (score: {entity['score']:.3f})")
        
        # Show anonymized version
        anonymized = detector.anonymize_text(test_text)
        print(f"Anonymized: {anonymized}")


if __name__ == "__main__":
    main()
