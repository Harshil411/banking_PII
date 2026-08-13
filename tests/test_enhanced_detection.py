#!/usr/bin/env python3
"""
Test Enhanced PII Detection System
"""

import sys
import json
from pathlib import Path
from enhanced_pii_detector import EnhancedPIIDetector

def test_enhanced_detection():
    """Test the enhanced PII detection system"""
    print("🔍 Testing Enhanced PII Detection System")
    print("=" * 50)
    
    # Initialize detector
    try:
        detector = EnhancedPIIDetector(
            bert_model_path="bert-base-multilingual-cased_100k_v1",
            llama_model_path="llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1",
            schema_path="data_schema.json"
        )
        print("✅ Enhanced PII Detector initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize detector: {e}")
        return False
    
    # Test cases covering all PII categories from schema
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
        
        try:
            # Run comprehensive detection
            results = detector.detect_comprehensive(test_case['text'])
            
            # Extract detected categories
            detected_categories = [entity['entity_group'] for entity in results['entities']]
            unique_categories = list(set(detected_categories))
            
            print(f"Detected categories: {unique_categories}")
            print(f"Expected categories: {test_case['expected_categories']}")
            print(f"Methods used: {results['summary']['methods_used']}")
            print(f"Total entities: {results['summary']['total_entities']}")
            print(f"Average confidence: {results['summary']['avg_confidence']:.3f}")
            
            # Check if expected categories were detected
            expected_found = [cat for cat in test_case['expected_categories'] if cat in unique_categories]
            coverage = len(expected_found) / len(test_case['expected_categories']) if test_case['expected_categories'] else 1.0
            
            print(f"Coverage: {coverage:.1%} ({len(expected_found)}/{len(test_case['expected_categories'])})")
            
            # Show individual entities
            for entity in results['entities']:
                print(f"  - {entity['entity_group']}: '{entity['word']}' (score: {entity['score']:.3f}, method: {entity.get('method', 'unknown')})")
            
            # Test anonymization
            anonymized = detector.anonymize_text(test_case['text'])
            print(f"Anonymized: {anonymized}")
            
            # Consider test passed if coverage is >= 70%
            if coverage >= 0.7:
                print("✅ PASSED")
                passed_tests += 1
            else:
                print("❌ FAILED - Low coverage")
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    try:
        detector = EnhancedPIIDetector(
            bert_model_path="bert-base-multilingual-cased_100k_v1",
            llama_model_path="llama-ai4privacy-multilingual-categorical-anonymiser-openpii_100k_v1",
            schema_path="data_schema.json"
        )
    except Exception as e:
        print(f"❌ Failed to initialize detector: {e}")
        return False
    
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
    
    for test_group in improvement_tests:
        category = test_group['category']
        print(f"\n🎯 Testing {category} detection:")
        
        for test_text in test_group['test_cases']:
            results = detector.detect_comprehensive(test_text)
            detected = [e for e in results['entities'] if e['entity_group'] == category]
            
            if detected:
                print(f"  ✅ '{test_text}' -> {detected[0]['word']} (score: {detected[0]['score']:.3f})")
            else:
                print(f"  ❌ '{test_text}' -> No {category} detected")
    
    return True

def main():
    """Main test function"""
    print("🚀 Enhanced PII Detection Test Suite")
    print("=" * 50)
    
    # Test 1: Basic functionality
    success1 = test_enhanced_detection()
    
    # Test 2: Specific improvements
    success2 = test_specific_improvements()
    
    # Overall result
    if success1 and success2:
        print("\n🎉 All tests passed! Enhanced PII detection is working correctly.")
        return True
    else:
        print("\n⚠️  Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
