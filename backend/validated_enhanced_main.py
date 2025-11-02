from pathlib import Path
import json
from typing import List, Optional, Dict, Any
import re

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# --- Paths ---
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BERT_DIR = WORKSPACE_ROOT / "bert-base-multilingual-cased_100k_v1"
LLAMA_DIR = WORKSPACE_ROOT / "llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1"
DATA_SCHEMA_FILE = WORKSPACE_ROOT / "data_schema.json"

# --- Enhanced PII Detection with Validation ---
class ValidatedEnhancedPIIDetector:
    def __init__(self, schema_path: str):
        self.schema_path = Path(schema_path)
        self.device = 0 if torch.cuda.is_available() else -1
        
        # Load data schema
        with open(self.schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)
        
        # Compile validation patterns from schema
        self.validation_patterns = {}
        for category, config in self.schema.items():
            try:
                pattern = config['regex']
                self.validation_patterns[category] = re.compile(pattern)
            except Exception as e:
                print(f"⚠️  Warning: Could not compile validation pattern for {category}: {e}")
                self.validation_patterns[category] = None
        
        # Compile enhanced detection patterns
        self._compile_enhanced_patterns()
    
    def _compile_enhanced_patterns(self):
        """Compile enhanced regex patterns for better PII detection"""
        self.regex_patterns = {}
        
        # Enhanced patterns with better coverage
        enhanced_patterns = {
            'GIVENNAME': r'\b[A-Z][a-z]{2,20}\b',
            'SURNAME': r'\b[A-Z][a-z]{2,20}\b',
            'FULLNAME': r'\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',
            'TELEPHONENUM': r'(?:\+91[-\\s]?|0)?[6789]\\d{9}',
            'EMAIL': r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+',
            'CITY': r'\\b[A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*\\b',
            'BUILDINGNUM': r'\\b\\d{1,4}\\b',
            'STREET': r'\\b\\d+\\s+[A-Za-z0-9\\s]+(?:Street|Road|Avenue|Lane|Drive|Way|Boulevard|Place)\\b',
            'ZIPCODE': r'\\b\\d{6}\\b',
            'DATE': r'\\b\\d{2}[-/]\\d{2}[-/]\\d{4}\\b',
            'TIME': r'\\b\\d{2}:\\d{2}(?::\\d{2})?\\b',
            'AGE': r'\\b(?:age|aged)?\\s*\\d{1,3}\\b',
            'AADHAAR': r'\\b\\d{4}\\s\\d{4}\\s\\d{4}\\b',
            'PAN': r'\\b[A-Z]{3}[PFCHAT][A-Z]\\d{4}[A-Z]\\b',
            'VOTERID': r'\\b[A-Z]{3}\\d{7}\\b',
            'DRIVERLICENSENUM': r'\\b[A-Z]{2}[-\\s]?\\d{2}[-\\s]?\\d{4}[-\\s]?\\d{7}\\b',
            'ACCOUNTNUM': r'\\b\\d{9,18}\\b',
            'IFSC': r'\\b[A-Z]{4}0[A-Z0-9]{6}\\b',
            'CREDITCARDNUM': r'\\b\\d{4}\\s\\d{4}\\s\\d{4}\\s\\d{4}\\b',
            'TRANSACTIONID': r'\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\\b',
            'GENDER': r'\\b(M|F|Male|Female|MALE|FEMALE)\\b',
            'PASSPORTNUM': r'\\b[A-Z]\\d{7}\\b'
        }
        
        for category, pattern in enhanced_patterns.items():
            try:
                self.regex_patterns[category] = re.compile(pattern, re.IGNORECASE)
            except Exception as e:
                print(f"⚠️  Warning: Could not compile regex for {category}: {e}")
                self.regex_patterns[category] = None
    
    def validate_entity(self, category: str, text: str, confidence: float) -> Dict:
        """Validate a detected entity against the schema"""
        if category not in self.validation_patterns:
            return {
                'valid': False,
                'reason': f'Unknown category: {category}',
                'confidence': confidence
            }
        
        pattern = self.validation_patterns[category]
        if pattern is None:
            return {
                'valid': False,
                'reason': f'No validation pattern available for {category}',
                'confidence': confidence
            }
        
        # Check if the text matches the schema pattern exactly
        if pattern.match(text):
            return {
                'valid': True,
                'reason': 'Matches schema pattern',
                'confidence': confidence
            }
        else:
            return {
                'valid': False,
                'reason': f'Does not match schema pattern: {pattern.pattern}',
                'confidence': confidence
            }
    
    def detect_with_regex(self, text: str) -> List[Dict]:
        """Detect PII using enhanced regex patterns"""
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
                    'score': 0.95,  # High confidence for regex matches
                    'method': 'regex_enhanced'
                })
        
        return entities
    
    def detect_contextual_pii(self, text: str) -> List[Dict]:
        """Detect PII using contextual patterns"""
        entities = []
        
        # Contextual patterns
        patterns = [
            (r'(?:name|Name|NAME)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)', 'FULLNAME'),
            (r'(?:email|Email|EMAIL)\s*:?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', 'EMAIL'),
            (r'(?:phone|Phone|PHONE|mobile|Mobile|MOBILE)\s*:?\s*((?:\+91[-\\s]?|0)?[6789]\\d{9})', 'TELEPHONENUM'),
            (r'(?:address|Address|ADDRESS)\s*:?\s*([A-Za-z0-9\\s,]+(?:Street|Road|Avenue|Lane|Drive|Way|Boulevard|Place))', 'STREET'),
            (r'(?:city|City|CITY)\s*:?\s*([A-Za-z\\s]+)', 'CITY'),
            (r'(?:pincode|Pincode|PINCODE|zip|Zip|ZIP)\s*:?\s*(\\d{6})', 'ZIPCODE'),
            (r'(?:age|Age|AGE)\s*:?\s*(\\d{1,3})', 'AGE'),
            (r'(?:gender|Gender|GENDER|sex|Sex|SEX)\s*:?\s*(M|F|Male|Female|MALE|FEMALE)', 'GENDER'),
            (r'(?:pan|PAN|pan\s*number|PAN\s*Number)\s*:?\s*([A-Z]{3}[PFCHAT][A-Z]\\d{4}[A-Z])', 'PAN'),
            (r'(?:aadhaar|Aadhaar|AADHAAR|aadhar|Aadhar|AADHAR)\s*:?\s*(\\d{4}\\s\\d{4}\\s\\d{4})', 'AADHAAR'),
            (r'(?:passport|Passport|PASSPORT|passport\s*number|Passport\s*Number)\s*:?\s*([A-Z]\\d{7})', 'PASSPORTNUM'),
            (r'(?:account|Account|ACCOUNT|account\s*number|Account\s*Number)\s*:?\s*(\\d{9,18})', 'ACCOUNTNUM'),
            (r'(?:ifsc|IFSC|ifsc\s*code|IFSC\s*Code)\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})', 'IFSC'),
            (r'(?:credit\s*card|Credit\s*Card|CREDIT\s*CARD|card\s*number|Card\s*Number)\s*:?\s*(\\d{4}\\s\\d{4}\\s\\d{4}\\s\\d{4})', 'CREDITCARDNUM'),
            (r'(?:transaction|Transaction|TRANSACTION|txn|TXN|transaction\s*id|Transaction\s*ID)\s*:?\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})', 'TRANSACTIONID'),
            (r'(?:date|Date|DATE|dob|DOB|birth|Birth|BIRTH)\s*:?\s*(\\d{2}[-/]\\d{2}[-/]\\d{4})', 'DATE'),
            (r'(?:driver|Driver|DRIVER|license|License|LICENSE)\s*:?\s*([A-Z]{2}[-\\s]?\\d{2}[-\\s]?\\d{4}[-\\s]?\\d{7})', 'DRIVERLICENSENUM'),
        ]
        
        for pattern, category in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append({
                    'entity_group': category,
                    'word': match.group(1),
                    'start': match.start(1),
                    'end': match.end(1),
                    'score': 0.9,
                    'method': 'contextual'
                })
        
        return entities
    
    def detect_comprehensive(self, text: str, min_confidence: float = 0.5) -> Dict:
        """Comprehensive PII detection with validation"""
        results = {
            'text': text,
            'entities': [],
            'filtered_entities': [],
            'summary': {},
            'methods_used': []
        }
        
        # Method 1: Regex-based detection
        regex_entities = self.detect_with_regex(text)
        results['entities'].extend(regex_entities)
        if regex_entities:
            results['methods_used'].append('regex')
        
        # Method 2: Contextual detection
        contextual_entities = self.detect_contextual_pii(text)
        results['entities'].extend(contextual_entities)
        if contextual_entities:
            results['methods_used'].append('contextual')
        
        # Validate all entities against schema
        validated_entities = []
        filtered_count = 0
        
        for entity in results['entities']:
            category = entity['entity_group']
            text = entity['word']
            confidence = entity['score']
            
            validation = self.validate_entity(category, text, confidence)
            
            if validation['valid'] and confidence >= min_confidence:
                validated_entities.append({
                    **entity,
                    'validation': validation,
                    'status': 'VALID'
                })
            else:
                results['filtered_entities'].append({
                    **entity,
                    'validation': validation,
                    'status': 'FILTERED',
                    'filter_reason': validation['reason']
                })
                filtered_count += 1
        
        results['entities'] = validated_entities
        
        # Generate summary
        categories_found = list(set(e['entity_group'] for e in validated_entities))
        avg_confidence = sum(e['score'] for e in validated_entities) / len(validated_entities) if validated_entities else 0
        
        results['summary'] = {
            'total_entities': len(validated_entities),
            'filtered_entities': filtered_count,
            'categories_found': categories_found,
            'methods_used': list(set(results['methods_used'])),
            'avg_confidence': avg_confidence,
            'validation_rate': len(validated_entities) / (len(validated_entities) + filtered_count) if (len(validated_entities) + filtered_count) > 0 else 0
        }
        
        return results

# --- App ---
app = FastAPI(title="Validated Enhanced Banking PII Service", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
device = 0 if torch.cuda.is_available() else -1

_bert_pipe = None
_llama_pipe = None
_validated_detector = None

def _load_token_classifier(model_dir: Path):
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
				aggregation_strategy="first",
                device=device,
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
				aggregation_strategy="first",
                device=device,
            )
        except Exception as e:
            continue
    
    raise RuntimeError(f"All loading strategies failed for {model_dir}")

@app.on_event("startup")
def load_models():
    global _bert_pipe, _llama_pipe, _validated_detector
    
    print("Loading Validated Enhanced PII Detector...")
    try:
        _validated_detector = ValidatedEnhancedPIIDetector(str(DATA_SCHEMA_FILE))
        print("✅ Validated Enhanced PII Detector loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load Validated Enhanced PII Detector: {e}")
        _validated_detector = None
    
    print("Loading BERT model...")
    try:
        _bert_pipe = _load_token_classifier(BERT_DIR)
        print("✅ BERT model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load BERT model: {e}")
        _bert_pipe = None
    
    print("Loading LLaMA model...")
    try:
        _llama_pipe = _load_token_classifier(LLAMA_DIR)
        print("✅ LLaMA model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load LLaMA model: {e}")
        _llama_pipe = None
    
    if not _bert_pipe and not _llama_pipe and not _validated_detector:
        print("⚠️  Warning: No models loaded successfully!")

# --- Schemas ---
class TextPayload(BaseModel):
    text: str
    lang_hint: Optional[str] = None

class AnonymizePayload(BaseModel):
    text: str
    replacement: str = "[REDACTED]"

class ValidatedDetectionPayload(BaseModel):
    text: str
    use_regex: bool = True
    use_contextual: bool = True
    use_ml: bool = True
    min_confidence: float = 0.5

# --- Helpers ---
def _reconstruct_text_from_tokens(original_text: str, start: int, end: int) -> str:
    """Reconstruct the actual text from the original text using start/end positions"""
    return original_text[start:end]

def _predict(pipe, text: str):
    """Run ML model prediction"""
    if not text or not text.strip():
        return []
    try:
        results = pipe(text)
        normalized_results = []
        for r in results:
            try:
                # Use start/end positions to reconstruct the actual text from original
                start = int(r.get("start", 0)) if r.get("start") is not None else 0
                end = int(r.get("end", 0)) if r.get("end") is not None else 0
                
                # Reconstruct the actual text from the original text
                actual_word = _reconstruct_text_from_tokens(text, start, end)
                
                normalized_results.append({
                    "entity_group": r.get("entity_group") or r.get("entity") or "UNKNOWN",
                    "score": float(r.get("score", 0.0)) if r.get("score") is not None else 0.0,
                    "word": actual_word,  # Use reconstructed text instead of tokenized word
                    "start": start,
                    "end": end,
                    "method": "ml"
                })
            except (ValueError, TypeError) as e:
                continue
        return normalized_results
    except Exception as e:
        print(f"❌ ML inference error: {e}")
        return []

def _anonymize(text: str, entities: List[dict], replacement: str) -> str:
    """Anonymize detected PII in text"""
    if not entities:
        return text
    # Replace from end to start to preserve indices
    sorted_entities = sorted(entities, key=lambda x: x["start"], reverse=True)
    redacted = text
    for ent in sorted_entities:
        s, e = int(ent["start"]), int(ent["end"])
        redacted = redacted[:s] + replacement + redacted[e:]
    return redacted

# --- API Endpoints ---
@app.post("/api/validated/detect")
def validated_detect_pii(payload: ValidatedDetectionPayload):
    """Validated PII detection with schema validation"""
    if _validated_detector is None:
        raise HTTPException(status_code=503, detail="Validated PII Detector not loaded")
    
    # Use the validated detector
    results = _validated_detector.detect_comprehensive(
        payload.text,
        min_confidence=payload.min_confidence
    )
    
    return {
        "model": "validated_enhanced_multi_method",
        "entities": results['entities'],
        "filtered_entities": results['filtered_entities'],
        "summary": results['summary']
    }

@app.post("/api/validated/anonymize")
def validated_anonymize_pii(payload: AnonymizePayload):
    """Validated PII anonymization"""
    detection_result = validated_detect_pii(ValidatedDetectionPayload(
        text=payload.text,
        use_regex=True,
        use_contextual=True,
        use_ml=True,
        min_confidence=0.5
    ))
    
    entities = detection_result["entities"]
    redacted = _anonymize(payload.text, entities, payload.replacement)
    
    return {
        "model": "validated_enhanced_multi_method",
        "entities": entities,
        "filtered_entities": detection_result["filtered_entities"],
        "redacted": redacted,
        "summary": detection_result["summary"]
    }

@app.get("/api/data_schema")
def get_data_schema():
    schema = None
    if DATA_SCHEMA_FILE.exists():
        try:
            schema = json.loads(DATA_SCHEMA_FILE.read_text(encoding="utf-8"))
        except Exception:
            schema = None
    return {"schema": schema}

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "models": {
            "bert": _bert_pipe is not None,
            "llama": _llama_pipe is not None,
            "validated_enhanced": _validated_detector is not None
        },
        "device": "cuda" if device == 0 else "cpu"
    }

# --- Static Frontend ---
REACT_BUILD_DIR = WORKSPACE_ROOT / "frontend" / "build"
REACT_DEV_DIR = WORKSPACE_ROOT / "frontend" / "public"

if REACT_BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=REACT_BUILD_DIR, html=True), name="static")
elif REACT_DEV_DIR.exists():
    app.mount("/", StaticFiles(directory=REACT_DEV_DIR, html=True), name="static")

# For local run: uvicorn backend.validated_enhanced_main:app --reload
