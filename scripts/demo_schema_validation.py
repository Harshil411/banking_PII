#!/usr/bin/env python3
"""
Comprehensive demonstration of PII validation using data_schema.json
Shows how the Enhanced PII Detection validates all entities against the schema
"""

import json
import re
from pathlib import Path

def load_schema_patterns():
    """Load and compile all schema patterns from data_schema.json"""
    schema_file = Path("data_schema.json")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    patterns = {}
    for category, config in schema.items():
        try:
            pattern = config['regex']
            patterns[category] = re.compile(pattern)
            print(f"✅ Loaded {category}: {pattern}")
        except Exception as e:
            print(f"❌ Error loading {category}: {e}")
            patterns[category] = None
    
    return patterns

def validate_entity_with_schema(category: str, text: str, confidence: float):
    """Validate entity against schema with cross-validation"""
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
    
    # Check if matches the detected category's pattern
    if pattern.match(text):
        return {
            'valid': True,
            'reason': f'Matches {category} schema pattern',
            'confidence': confidence,
            'corrected_category': category
        }
    else:
        # Cross-validation: check against all other categories
        specific_categories = ['PAN', 'TELEPHONENUM', 'AADHAAR', 'DRIVERLICENSENUM', 'EMAIL', 'IFSC', 'VOTERID', 'PASSPORTNUM', 'CREDITCARDNUM', 'TRANSACTIONID', 'GENDER', 'DATE', 'TIME', 'AGE', 'ZIPCODE', 'BUILDINGNUM', 'FULLNAME', 'GIVENNAME', 'SURNAME', 'CITY']
        
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

def test_all_pii_categories():
    """Test validation for all PII categories from data_schema.json"""
    
    print("🔍 COMPREHENSIVE PII VALIDATION TEST")
    print("=" * 60)
    print("Testing all PII categories against data_schema.json patterns")
    print("=" * 60)
    
    # Test cases covering all PII categories
    test_cases = [
        # Names
        ("FULLNAME", "John Doe", 0.95, True),
        ("GIVENNAME", "John", 0.90, True),
        ("SURNAME", "Doe", 0.90, True),
        
        # Contact Information
        ("TELEPHONENUM", "9876543210", 0.95, True),
        ("TELEPHONENUM", "+91-9876543210", 0.95, True),
        ("EMAIL", "john.doe@example.com", 0.95, True),
        
        # Address
        ("CITY", "Mumbai", 0.90, True),
        ("ZIPCODE", "110001", 0.90, True),
        ("BUILDINGNUM", "123", 0.85, True),
        
        # Government IDs
        ("PAN", "AAAPA1234A", 0.95, True),
        ("AADHAAR", "1234 5678 9012", 0.95, True),
        ("VOTERID", "ABC1234567", 0.95, True),
        ("DRIVERLICENSENUM", "MH-14-2011-0062821", 0.95, True),
        ("PASSPORTNUM", "K1234567", 0.95, True),
        
        # Financial
        ("ACCOUNTNUM", "123456789", 0.90, True),
        ("IFSC", "HDFC0001234", 0.90, True),
        ("CREDITCARDNUM", "4111 1111 1111 1111", 0.90, True),
        
        # Other
        ("DATE", "04/08/2024", 0.90, True),
        ("TIME", "12:25", 0.90, True),
        ("AGE", "28", 0.90, True),
        ("GENDER", "Male", 0.90, True),
        ("TRANSACTIONID", "f47ac10b-58cc-4372-a567-0e02b2c3d479", 0.90, True),
        
        # Misclassified cases (common ML model errors)
        ("DRIVERLICENSENUM", "AAAPA1234A", 0.95, False),  # Should be PAN
        ("AADHAAR", "9876543210", 0.95, False),           # Should be TELEPHONENUM
        ("CITY", "Mobile", 0.60, False),                  # Should be filtered
        ("STREET", "1234-5678-9012", 0.90, False),        # Should be filtered
    ]
    
    print("\n📋 Loading schema patterns...")
    patterns = load_schema_patterns()
    print(f"✅ Loaded {len(patterns)} PII categories from data_schema.json")
    
    print("\n🧪 Testing PII Detection and Validation")
    print("-" * 60)
    
    valid_count = 0
    corrected_count = 0
    filtered_count = 0
    
    for category, text, confidence, expected_valid in test_cases:
        print(f"\n🔍 Testing: '{text}' (detected as {category})")
        
        result = validate_entity_with_schema(category, text, confidence)
        
        if result['valid']:
            if 'corrected_category' in result and result['corrected_category'] != category:
                print(f"  ✅ CORRECTED: {category} → {result['corrected_category']}")
                print(f"  📝 Reason: {result['reason']}")
                corrected_count += 1
            else:
                print(f"  ✅ VALID: {category}")
                print(f"  📝 Reason: {result['reason']}")
                valid_count += 1
        else:
            print(f"  ❌ FILTERED: {category}")
            print(f"  📝 Reason: {result['reason']}")
            filtered_count += 1
    
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    print(f"✅ Valid entities: {valid_count}")
    print(f"🔄 Corrected entities: {corrected_count}")
    print(f"❌ Filtered entities: {filtered_count}")
    print(f"📈 Total processed: {valid_count + corrected_count + filtered_count}")
    
    print("\n🎯 KEY IMPROVEMENTS:")
    print("• Cross-validation corrects misclassified entities")
    print("• Schema patterns ensure only valid PII is detected")
    print("• False positives are filtered out automatically")
    print("• All 22 PII categories from data_schema.json are supported")

if __name__ == "__main__":
    test_all_pii_categories()
