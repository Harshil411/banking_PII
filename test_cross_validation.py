#!/usr/bin/env python3
"""
Test the cross-validation functionality for PII detection
"""

import json
import re
from pathlib import Path

# Load schema patterns
def load_schema_patterns():
    schema_file = Path("data_schema.json")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    patterns = {}
    for category, config in schema.items():
        try:
            pattern = config['regex']
            patterns[category] = re.compile(pattern)
        except Exception as e:
            print(f"⚠️  Warning: Could not compile pattern for {category}: {e}")
            patterns[category] = None
    
    return patterns

def validate_entity(category: str, text: str, confidence: float):
    """Validate a detected entity against the schema with cross-validation"""
    patterns = load_schema_patterns()
    
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

# Test cases
test_cases = [
    ("DRIVERLICENSENUM", "AAAPA1234A", 0.99),  # Should be corrected to PAN
    ("AADHAAR", "9876543210", 0.99),           # Should be corrected to TELEPHONENUM
    ("CITY", "Mobile", 0.59),                  # Should be filtered out
    ("PAN", "AAAPA1234A", 0.99),               # Should be valid
    ("TELEPHONENUM", "9876543210", 0.99),      # Should be valid
]

print("🧪 Testing Cross-Validation System")
print("=" * 50)

for category, text, confidence in test_cases:
    print(f"\n🔍 Testing: '{text}' (detected as {category})")
    result = validate_entity(category, text, confidence)
    
    if result['valid']:
        if 'corrected_category' in result and result['corrected_category'] != category:
            print(f"  ✅ CORRECTED: {category} → {result['corrected_category']}")
            print(f"  📝 Reason: {result['reason']}")
        else:
            print(f"  ✅ VALID: {category}")
            print(f"  📝 Reason: {result['reason']}")
    else:
        print(f"  ❌ FILTERED: {category}")
        print(f"  📝 Reason: {result['reason']}")

print("\n" + "=" * 50)
print("✅ Cross-validation test completed!")
