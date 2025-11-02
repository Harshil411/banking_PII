from pathlib import Path
import json
import re
from typing import List, Optional, Dict

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
DATA_SCHEMA_DESC_FILE = WORKSPACE_ROOT / "data_schema_description.txt"
METRICS_FILES = [
	WORKSPACE_ROOT / "metrics_summary.json",
	WORKSPACE_ROOT / "metrics_summary 1.json",
	WORKSPACE_ROOT / "eval_bert-base-multilingual-cased_100k_v1" / "metrics_summary.json",
	WORKSPACE_ROOT / "eval_llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1" / "metrics_summary.json",
]

# --- App ---
app = FastAPI(title="Banking PII Service", version="1.0.0")

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
_schema_patterns = None

# --- Schema Validation ---
def _load_schema_patterns():
    """Load and compile schema validation patterns"""
    global _schema_patterns
    if _schema_patterns is not None:
        return _schema_patterns
    
    try:
        with open(DATA_SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        _schema_patterns = {}
        for category, config in schema.items():
            try:
                pattern = config['regex']
                _schema_patterns[category] = re.compile(pattern)
            except Exception as e:
                print(f"⚠️  Warning: Could not compile pattern for {category}: {e}")
                _schema_patterns[category] = None
        
        return _schema_patterns
    except Exception as e:
        print(f"❌ Failed to load schema patterns: {e}")
        return {}

def validate_entity(category: str, text: str, confidence: float) -> Dict:
    """Validate a detected entity against the schema with cross-validation"""
    patterns = _load_schema_patterns()
    
    if category not in patterns:
        return {
            'valid': False,
            'reason': f'Unknown category: {category}',
            'confidence': confidence
        }
    
    pattern = patterns[category]
    if pattern is None:
        return {
            'valid': False,
            'reason': f'No validation pattern available for {category}',
            'confidence': confidence
        }
    
    # Check if the text matches the detected category's schema pattern
    if pattern.match(text):
        return {
            'valid': True,
            'reason': f'Matches {category} schema pattern',
            'confidence': confidence,
            'corrected_category': category
        }
    else:
        # Cross-validation: check if it matches any other category's pattern
        # Prioritize specific patterns over generic ones (like STREET with .*)
        specific_categories = ['PAN', 'TELEPHONENUM', 'AADHAAR', 'DRIVERLICENSENUM', 'EMAIL', 'IFSC', 'VOTERID', 'PASSPORTNUM', 'CREDITCARDNUM', 'TRANSACTIONID', 'GENDER', 'DATE', 'TIME', 'AGE', 'ZIPCODE', 'BUILDINGNUM']
        
        # First check specific categories
        for other_category in specific_categories:
            if other_category in patterns and patterns[other_category] and patterns[other_category].match(text):
                return {
                    'valid': True,
                    'reason': f'Cross-validated: matches {other_category} pattern instead of {category}',
                    'confidence': confidence,
                    'corrected_category': other_category,
                    'original_category': category
                }
        
        # Then check other categories (excluding STREET with .* pattern)
        for other_category, other_pattern in patterns.items():
            if (other_category != 'STREET' and other_pattern and 
                other_pattern.pattern != '.*' and other_pattern.match(text)):
                return {
                    'valid': True,
                    'reason': f'Cross-validated: matches {other_category} pattern instead of {category}',
                    'confidence': confidence,
                    'corrected_category': other_category,
                    'original_category': category
                }
        
        return {
            'valid': False,
            'reason': f'Does not match {category} schema pattern: {pattern.pattern}',
            'confidence': confidence
        }


def _load_token_classifier(model_dir: Path):
	if not model_dir.exists():
		raise FileNotFoundError(f"Model directory not found: {model_dir}")
	
	# Special handling for LLaMA model with tokenizer issues
	if "llama" in str(model_dir).lower():
		print("🦙 Detected LLaMA model, using special loading approach...")
		try:
			# Try to load model first, then create a basic tokenizer
			model = AutoModelForTokenClassification.from_pretrained(model_dir)
			
			# Create a basic tokenizer that doesn't rely on the corrupted tokenizer.json
			from transformers import PreTrainedTokenizerFast
			from tokenizers import Tokenizer
			
			# Try to create a simple tokenizer
			tokenizer = AutoTokenizer.from_pretrained(
				"bert-base-multilingual-cased",  # Use BERT tokenizer as fallback
				use_fast=True
			)
			
			print("✅ LLaMA model loaded with BERT tokenizer fallback")
			return pipeline(
				task="token-classification",
				model=model,
				tokenizer=tokenizer,
				aggregation_strategy="first",
				device=device,
			)
		except Exception as e:
			print(f"❌ LLaMA special loading failed: {e}")
			# Continue with normal loading strategies
	
	# Try different loading strategies
	loading_strategies = [
		{"trust_remote_code": True, "use_fast": False},
		{"trust_remote_code": False, "use_fast": False},
		{"trust_remote_code": False, "use_fast": True},
		{"trust_remote_code": True, "use_fast": True},
		{"local_files_only": True, "use_fast": False},
		{"local_files_only": True, "use_fast": True},
	]
	
	last_error = None
	for i, strategy in enumerate(loading_strategies):
		try:
			print(f"🔄 Trying loading strategy {i+1}: {strategy}")
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
			print(f"❌ Strategy {i+1} failed: {e}")
			last_error = e
			continue
	
	raise RuntimeError(f"All tokenizer loading strategies failed. Last error: {last_error}")


@app.on_event("startup")
def load_models():
	global _bert_pipe, _llama_pipe
	
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
	
	if not _bert_pipe and not _llama_pipe:
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
	if not text or not text.strip():
		return []
	try:
		print(f"🔍 Running inference on text: '{text[:50]}...'")
		results = pipe(text)
		print(f"📊 Raw results: {results}")
		
		# Normalize scores/labels with better error handling
		normalized_results = []
		for i, r in enumerate(results):
			try:
				print(f"🔍 Processing result {i}: {r}")
				
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
				})
			except (ValueError, TypeError) as e:
				print(f"⚠️  Skipping malformed result: {r}, error: {e}")
				continue
		print(f"✅ Normalized results: {normalized_results}")
		return normalized_results
	except Exception as e:
		print(f"❌ Inference error details: {e}")
		import traceback
		traceback.print_exc()
		raise HTTPException(status_code=500, detail=f"Inference error: {e}")


def _anonymize(text: str, entities: List[dict], replacement: str) -> str:
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


@app.get("/api/metrics")
def get_metrics():
	collected = {}
	for f in METRICS_FILES:
		if f.exists():
			try:
				with f.open("r", encoding="utf-8") as fh:
					collected[str(f.relative_to(WORKSPACE_ROOT))] = json.load(fh)
			except Exception:
				# Ignore unreadable files
				pass
	return collected


@app.get("/api/data_schema")
def get_data_schema():
	schema = None
	schema_desc = None
	if DATA_SCHEMA_FILE.exists():
		try:
			schema = json.loads(DATA_SCHEMA_FILE.read_text(encoding="utf-8"))
		except Exception:
			schema = None
	if DATA_SCHEMA_DESC_FILE.exists():
		try:
			schema_desc = DATA_SCHEMA_DESC_FILE.read_text(encoding="utf-8")
		except Exception:
			schema_desc = None
	return {"schema": schema, "description": schema_desc}


@app.get("/api/health")
def health_check():
	return {
		"status": "healthy",
		"models": {
			"bert": _bert_pipe is not None,
			"llama": _llama_pipe is not None,
			"validated_enhanced": True
		},
		"device": "cuda" if device == 0 else "cpu"
	}

# --- Validated Endpoints ---
@app.post("/api/validated/detect")
def validated_detect_pii(payload: ValidatedDetectionPayload):
	"""Validated PII detection with schema validation"""
	if not payload.text.strip():
		return {
			"model": "validated_enhanced",
			"entities": [],
			"filtered_entities": [],
			"summary": {
				"total_entities": 0,
				"filtered_entities": 0,
				"categories_found": [],
				"methods_used": [],
				"avg_confidence": 0,
				"validation_rate": 0
			}
		}
	
	# Get entities from existing models
	all_entities = []
	
	if payload.use_ml and _bert_pipe:
		try:
			bert_entities = _predict(_bert_pipe, payload.text)
			all_entities.extend(bert_entities)
		except Exception as e:
			print(f"❌ BERT detection error: {e}")
	
	if payload.use_ml and _llama_pipe:
		try:
			llama_entities = _predict(_llama_pipe, payload.text)
			all_entities.extend(llama_entities)
		except Exception as e:
			print(f"❌ LLaMA detection error: {e}")
	
	# Validate all entities against schema
	valid_entities = []
	filtered_entities = []
	
	for entity in all_entities:
		category = entity['entity_group']
		text = entity['word']
		confidence = entity['score']
		
		validation = validate_entity(category, text, confidence)
		
		if validation['valid'] and confidence >= payload.min_confidence:
			# Use corrected category if cross-validation found a better match
			corrected_entity = {
				**entity,
				'validation': validation,
				'status': 'VALID'
			}
			
			# Update category if cross-validation corrected it
			if 'corrected_category' in validation:
				corrected_entity['entity_group'] = validation['corrected_category']
				corrected_entity['original_category'] = category
			
			valid_entities.append(corrected_entity)
		else:
			filtered_entities.append({
				**entity,
				'validation': validation,
				'status': 'FILTERED',
				'filter_reason': validation['reason']
			})
	
	# Generate summary
	categories_found = list(set(e['entity_group'] for e in valid_entities))
	avg_confidence = sum(e['score'] for e in valid_entities) / len(valid_entities) if valid_entities else 0
	total_detected = len(valid_entities) + len(filtered_entities)
	validation_rate = len(valid_entities) / total_detected if total_detected > 0 else 0
	
	return {
		"model": "validated_enhanced",
		"entities": valid_entities,
		"filtered_entities": filtered_entities,
		"summary": {
			"total_entities": len(valid_entities),
			"filtered_entities": len(filtered_entities),
			"categories_found": categories_found,
			"methods_used": ["ml"] if payload.use_ml else [],
			"avg_confidence": avg_confidence,
			"validation_rate": validation_rate
		}
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
		"model": "validated_enhanced",
		"entities": entities,
		"filtered_entities": detection_result["filtered_entities"],
		"redacted": redacted,
		"summary": detection_result["summary"]
	}


# --- Static Frontend ---
# Serve React build in production, development files in dev
REACT_BUILD_DIR = WORKSPACE_ROOT / "frontend" / "build"
REACT_DEV_DIR = WORKSPACE_ROOT / "frontend" / "public"

if REACT_BUILD_DIR.exists():
    # Production: Serve React build
    app.mount("/", StaticFiles(directory=REACT_BUILD_DIR, html=True), name="static")
elif REACT_DEV_DIR.exists():
    # Development: Serve basic HTML
    app.mount("/", StaticFiles(directory=REACT_DEV_DIR, html=True), name="static")


# For local run: uvicorn backend.main:app --reload
