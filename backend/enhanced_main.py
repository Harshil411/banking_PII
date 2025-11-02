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

# --- Enhanced PII Detection Class ---
class EnhancedPIIDetector:
    def __init__(self, schema_path: str):
        self.schema_path = Path(schema_path)
        self.device = 0 if torch.cuda.is_available() else -1
        
        # Load data schema
        with open(self.schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)
        
        # Compile enhanced regex patterns
        self._compile_enhanced_patterns()
    
    def _compile_enhanced_patterns(self):
        """Compile enhanced regex patterns for better PII detection"""
        self.regex_patterns = {}
        
        # Enhanced patterns with better coverage
        enhanced_patterns = {
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
            'AGE': r'\\b(?:age|aged)?\s*\\d{1,3}\\b',
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
    
    def detect_name_patterns(self, text: str) -> List[Dict]:
        """Enhanced name detection using multiple patterns"""
        entities = []
        
        # Pattern 1: Full names (First Last)
        fullname_pattern = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
        for match in re.finditer(fullname_pattern, text):
            entities.append({
                'entity_group': 'FULLNAME',
                'word': match.group(),
                'start': match.start(),
                'end': match.end(),
                'score': 0.9,
                'method': 'name_pattern'
            })
        
        # Pattern 2: Indian names with common prefixes/suffixes
        indian_name_pattern = r'\b[A-Z][a-z]+\s+(?:Kumar|Singh|Sharma|Verma|Mehta|Patel|Gupta|Agarwal|Jain|Shah)\b'
        for match in re.finditer(indian_name_pattern, text):
            entities.append({
                'entity_group': 'FULLNAME',
                'word': match.group(),
                'start': match.start(),
                'end': match.end(),
                'score': 0.95,
                'method': 'indian_name_pattern'
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

# --- App ---
app = FastAPI(title="Enhanced Banking PII Service", version="2.0.0")

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
_enhanced_detector = None

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
    global _bert_pipe, _llama_pipe, _enhanced_detector
    
    print("Loading Enhanced PII Detector...")
    try:
        _enhanced_detector = EnhancedPIIDetector(str(DATA_SCHEMA_FILE))
        print("✅ Enhanced PII Detector loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load Enhanced PII Detector: {e}")
        _enhanced_detector = None
    
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
    
    if not _bert_pipe and not _llama_pipe and not _enhanced_detector:
        print("⚠️  Warning: No models loaded successfully!")

# --- Schemas ---
class TextPayload(BaseModel):
    text: str
    lang_hint: Optional[str] = None

class AnonymizePayload(BaseModel):
    text: str
    replacement: str = "[REDACTED]"

class EnhancedDetectionPayload(BaseModel):
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

def _merge_entities(entities: List[Dict]) -> List[Dict]:
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
@app.post("/api/enhanced/detect")
def enhanced_detect_pii(payload: EnhancedDetectionPayload):
    """Enhanced PII detection using multiple methods"""
    if _enhanced_detector is None:
        raise HTTPException(status_code=503, detail="Enhanced PII Detector not loaded")
    
    entities = []
    methods_used = []
    
    # Regex-based detection
    if payload.use_regex:
        regex_entities = _enhanced_detector.detect_with_regex(payload.text)
        entities.extend(regex_entities)
        if regex_entities:
            methods_used.append("regex")
    
    # Contextual detection
    if payload.use_contextual:
        contextual_entities = _enhanced_detector.detect_contextual_pii(payload.text)
        entities.extend(contextual_entities)
        if contextual_entities:
            methods_used.append("contextual")
        
        # Enhanced name detection
        name_entities = _enhanced_detector.detect_name_patterns(payload.text)
        entities.extend(name_entities)
        if name_entities:
            methods_used.append("name_patterns")
    
    # ML-based detection
    if payload.use_ml:
        if _bert_pipe:
            bert_entities = _predict(_bert_pipe, payload.text)
            entities.extend(bert_entities)
            methods_used.append("bert")
        
        if _llama_pipe:
            llama_entities = _predict(_llama_pipe, payload.text)
            entities.extend(llama_entities)
            methods_used.append("llama")
    
    # Filter by confidence
    entities = [e for e in entities if e['score'] >= payload.min_confidence]
    
    # Merge overlapping entities
    entities = _merge_entities(entities)
    
    # Generate summary
    categories_found = list(set(e['entity_group'] for e in entities))
    avg_confidence = sum(e['score'] for e in entities) / len(entities) if entities else 0
    
    return {
        "model": "enhanced_multi_method",
        "entities": entities,
        "summary": {
            "total_entities": len(entities),
            "categories_found": categories_found,
            "methods_used": list(set(methods_used)),
            "avg_confidence": avg_confidence
        }
    }

@app.post("/api/enhanced/anonymize")
def enhanced_anonymize_pii(payload: AnonymizePayload):
    """Enhanced PII anonymization"""
    detection_result = enhanced_detect_pii(EnhancedDetectionPayload(
        text=payload.text,
        use_regex=True,
        use_contextual=True,
        use_ml=True,
        min_confidence=0.5
    ))
    
    entities = detection_result["entities"]
    redacted = _anonymize(payload.text, entities, payload.replacement)
    
    return {
        "model": "enhanced_multi_method",
        "entities": entities,
        "redacted": redacted,
        "summary": detection_result["summary"]
    }

# Legacy endpoints for backward compatibility
@app.post("/api/bert/extract")
def extract_pii_bert(payload: TextPayload):
    if _bert_pipe is None:
        raise HTTPException(status_code=503, detail="BERT model not loaded")
    entities = _predict(_bert_pipe, payload.text)
    return {"model": "bert-base-multilingual-cased_100k_v1", "entities": entities}

@app.post("/api/llama/anonymize")
def anonymize_pii_llama(payload: AnonymizePayload):
    if _llama_pipe is None:
        raise HTTPException(status_code=503, detail="LLaMA model not loaded")
    entities = _predict(_llama_pipe, payload.text)
    redacted = _anonymize(payload.text, entities, payload.replacement)
    return {
        "model": "llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1",
        "entities": entities,
        "redacted": redacted,
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
            "enhanced": _enhanced_detector is not None
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

# For local run: uvicorn backend.enhanced_main:app --reload
