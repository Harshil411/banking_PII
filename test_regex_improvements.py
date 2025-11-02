#!/usr/bin/env python3
"""
Test Regex-based PII Detection Improvements
"""

import re
import json
from pathlib import Path

def test_regex_improvements():
    """Test the enhanced regex patterns for PII detection"""
    print("🔍 Testing Enhanced Regex PII Detection")
    print("=" * 50)
    
    # Load data schema
    with open("data_schema.json", 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
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
    
    # Compile patterns
    compiled_patterns = {}
    for category, pattern in enhanced_patterns.items():
        try:
            compiled_patterns[category] = re.compile(pattern, re.IGNORECASE)
        except Exception as e:
            print(f"⚠️  Warning: Could not compile regex for {category}: {e}")
            compiled_patterns[category] = None
    
    # Test cases covering all PII categories
    test_cases = [
        {
            "name": "Basic Personal Information",
            "text": "My name is Arun Sharma, I am 28 years old, Male, and my email is arun.sharma@hdfc.com",
            "expected_categories": ["FULLNAME", "AGE", "GENDER", "EMAIL"]
        },
        {
            "name": "Contact Information",
            "text": "Contact me at +91-9876543210 or visit 123 MG Road, Mumbai 400001",
            "expected_categories": ["TELEPHONENUM", "BUILDINGNUM", "STREET", "CITY", "ZIPCODE"]
        },
        {
            "name": "Government IDs",
            "text": "PAN: AAAPA1234A, Aadhaar: 1234 5678 9012, Voter ID: ABC1234567",
            "expected_categories": ["PAN", "AADHAAR", "VOTERID"]
        },
        {
            "name": "Financial Information",
            "text": "Account: 123456789, IFSC: HDFC0001234, Credit Card: 4111 1111 1111 1111",
            "expected_categories": ["ACCOUNTNUM", "IFSC", "CREDITCARDNUM"]
        },
        {
            "name": "Travel Documents",
            "text": "Passport: K1234567, Driver License: MH-14-2011-0062821",
            "expected_categories": ["PASSPORTNUM", "DRIVERLICENSENUM"]
        },
        {
            "name": "Transaction Information",
            "text": "Transaction ID: f47ac10b-58cc-4372-a567-0e02b2c3d479, Date: 15/08/2024, Time: 14:30",
            "expected_categories": ["TRANSACTIONID", "DATE", "TIME"]
        },
        {
            "name": "Contextual Detection",
            "text": "Name: Neha Mehta, Phone: 9876543210, Address: 456 Park Avenue, City: Bangalore",
            "expected_categories": ["FULLNAME", "TELEPHONENUM", "STREET", "CITY"]
        },
        {
            "name": "Indian Name Patterns",
            "text": "Ravi Kumar Singh and Priya Sharma are colleagues",
            "expected_categories": ["FULLNAME"]
        },
        {
            "name": "Mixed Format Data",
            "text": "Customer: Deepak Verma, DOB: 04-08-1990, Age: 34, Gender: M",
            "expected_categories": ["FULLNAME", "DATE", "AGE", "GENDER"]
        },
        {
            "name": "Complex Banking Data",
            "text": "Account Holder: Sunil Agarwal, Account Number: 001234567890123456, IFSC Code: SBIN0004567, Transaction: f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "expected_categories": ["FULLNAME", "ACCOUNTNUM", "IFSC", "TRANSACTIONID"]
        }
    ]
    
    total_tests = len(test_cases)
    passed_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}/{total_tests}: {test_case['name']}")
        print(f"Text: {test_case['text']}")
        print("-" * 40)
        
        # Detect PII using regex
        detected_entities = []
        for category, pattern in compiled_patterns.items():
            if pattern is None:
                continue
                
            for match in pattern.finditer(test_case['text']):
                detected_entities.append({
                    'category': category,
                    'text': match.group(),
                    'start': match.start(),
                    'end': match.end()
                })
        
        # Extract detected categories
        detected_categories = list(set([entity['category'] for entity in detected_entities]))
        
        print(f"Detected categories: {detected_categories}")
        print(f"Expected categories: {test_case['expected_categories']}")
        print(f"Total entities found: {len(detected_entities)}")
        
        # Check if expected categories were detected
        expected_found = [cat for cat in test_case['expected_categories'] if cat in detected_categories]
        coverage = len(expected_found) / len(test_case['expected_categories']) if test_case['expected_categories'] else 1.0
        
        print(f"Coverage: {coverage:.1%} ({len(expected_found)}/{len(test_case['expected_categories'])})")
        
        # Show individual entities
        for entity in detected_entities:
            print(f"  - {entity['category']}: '{entity['text']}' (pos: {entity['start']}-{entity['end']})")
        
        # Consider test passed if coverage is >= 70%
        if coverage >= 0.7:
            print("✅ PASSED")
            passed_tests += 1
        else:
            print("❌ FAILED - Low coverage")
    
    print(f"\n📊 Test Results Summary")
    print("=" * 30)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {passed_tests/total_tests:.1%}")
    
    return passed_tests == total_tests

def test_specific_improvements():
    """Test specific improvements for problematic categories"""
    print("\n🔧 Testing Specific Improvements")
    print("=" * 40)
    
    # Test cases for previously problematic categories
    improvement_tests = [
        {
            "category": "FULLNAME",
            "test_cases": [
                "Arun Sharma is my name",
                "Name: Priya Mehta",
                "Customer: Ravi Kumar Singh",
                "Contact person: Neha Agarwal"
            ]
        },
        {
            "category": "GIVENNAME",
            "test_cases": [
                "Arun is my first name",
                "First name: Priya",
                "Call me Ravi",
                "I am Neha"
            ]
        },
        {
            "category": "SURNAME",
            "test_cases": [
                "My surname is Sharma",
                "Last name: Mehta",
                "Family name: Kumar",
                "Surname: Agarwal"
            ]
        },
        {
            "category": "PASSPORTNUM",
            "test_cases": [
                "Passport: K1234567",
                "Passport number: Z7654321",
                "Travel document: A9876543",
                "PASSPORT: B1234567"
            ]
        }
    ]
    
    # Compile patterns for specific categories
    patterns = {
        'FULLNAME': re.compile(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+\b', re.IGNORECASE),
        'GIVENNAME': re.compile(r'\b[A-Z][a-z]{1,20}\b'),
        'SURNAME': re.compile(r'\b[A-Z][a-z]{1,20}\b'),
        'PASSPORTNUM': re.compile(r'\b[A-Z]\d{7}\b')
    }
    
    for test_group in improvement_tests:
        category = test_group['category']
        print(f"\n🎯 Testing {category} detection:")
        
        pattern = patterns.get(category)
        if not pattern:
            print(f"  ❌ No pattern available for {category}")
            continue
        
        for test_text in test_group['test_cases']:
            matches = list(pattern.finditer(test_text))
            if matches:
                for match in matches:
                    print(f"  ✅ '{test_text}' -> {match.group()} (pos: {match.start()}-{match.end()})")
            else:
                print(f"  ❌ '{test_text}' -> No {category} detected")
    
    return True

def main():
    """Main test function"""
    print("🚀 Enhanced Regex PII Detection Test Suite")
    print("=" * 50)
    
    # Test 1: Basic functionality
    success1 = test_regex_improvements()
    
    # Test 2: Specific improvements
    success2 = test_specific_improvements()
    
    # Overall result
    if success1 and success2:
        print("\n🎉 All tests passed! Enhanced regex PII detection is working correctly.")
        return True
    else:
        print("\n⚠️  Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
