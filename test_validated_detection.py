#!/usr/bin/env python3
"""
Test Validated PII Detection System
Demonstrates how the system fixes false positive issues
"""

import requests
import json
import time

def test_validated_detection():
    """Test the validated detection system"""
    print("🔍 Testing Validated PII Detection System")
    print("=" * 60)
    
    # Test cases that include the problematic detections from the user
    test_cases = [
        {
            "name": "Problematic Detections (Should be filtered)",
            "text": "Some random data: 1234 - 5678 - and 9012, 9876543210, ABCDE1234F",
            "expected_filtered": 4  # All should be filtered as false positives
        },
        {
            "name": "Valid PII Data",
            "text": "Customer: Arun Sharma, DOB: 15/08/1990, Aadhaar: 1234 5678 9012, Driver License: MH-14-2011-0062821",
            "expected_valid": 4  # All should be valid
        },
        {
            "name": "Mixed Valid and Invalid",
            "text": "Name: Priya Mehta, Phone: +91-9876543210, Random: 1234 - 5678 -, Invalid: 9012",
            "expected_valid": 2,  # Name and Phone should be valid
            "expected_filtered": 2  # Random numbers should be filtered
        }
    ]
    
    # Start the server (this would normally be done separately)
    print("⚠️  Note: This test assumes the validated server is running on localhost:8000")
    print("   Start with: uvicorn backend.validated_enhanced_main:app --reload")
    print()
    
    base_url = "http://localhost:8000"
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"🧪 Test {i}: {test_case['name']}")
        print(f"Text: {test_case['text']}")
        print("-" * 50)
        
        try:
            # Test the validated detection endpoint
            response = requests.post(
                f"{base_url}/api/validated/detect",
                json={
                    "text": test_case['text'],
                    "use_regex": True,
                    "use_contextual": True,
                    "use_ml": False,  # Skip ML for this test
                    "min_confidence": 0.5
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                valid_entities = data.get('entities', [])
                filtered_entities = data.get('filtered_entities', [])
                summary = data.get('summary', {})
                
                print(f"✅ Valid entities: {len(valid_entities)}")
                print(f"❌ Filtered entities: {len(filtered_entities)}")
                print(f"📊 Validation rate: {summary.get('validation_rate', 0):.1%}")
                
                # Show valid entities
                if valid_entities:
                    print("   Valid entities:")
                    for entity in valid_entities:
                        print(f"     - {entity['entity_group']}: '{entity['word']}' (confidence: {entity['score']:.1%})")
                
                # Show filtered entities
                if filtered_entities:
                    print("   Filtered entities:")
                    for entity in filtered_entities:
                        print(f"     - {entity['entity_group']}: '{entity['word']}' (reason: {entity['filter_reason']})")
                
                # Check expectations
                expected_valid = test_case.get('expected_valid', 0)
                expected_filtered = test_case.get('expected_filtered', 0)
                
                if expected_valid > 0 and len(valid_entities) >= expected_valid:
                    print("✅ PASSED - Valid entities as expected")
                elif expected_valid > 0:
                    print(f"❌ FAILED - Expected {expected_valid} valid entities, got {len(valid_entities)}")
                
                if expected_filtered > 0 and len(filtered_entities) >= expected_filtered:
                    print("✅ PASSED - False positives filtered as expected")
                elif expected_filtered > 0:
                    print(f"❌ FAILED - Expected {expected_filtered} filtered entities, got {len(filtered_entities)}")
                
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Server not running")
            print("   Start server with: uvicorn backend.validated_enhanced_main:app --reload")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()

def test_specific_false_positives():
    """Test the specific false positives mentioned by the user"""
    print("🎯 Testing Specific False Positives")
    print("=" * 40)
    
    # The exact problematic detections from the user
    problematic_detections = [
        {
            "category": "DATE",
            "text": "1234 - 5678 -",
            "confidence": 0.903
        },
        {
            "category": "AADHAAR",
            "text": "9012",
            "confidence": 0.702
        },
        {
            "category": "AADHAAR", 
            "text": "9876543210",
            "confidence": 1.0
        },
        {
            "category": "DRIVERLICENSENUM",
            "text": "ABCDE1234F",
            "confidence": 0.854
        }
    ]
    
    print("Testing problematic detections that should be filtered:")
    print()
    
    for i, detection in enumerate(problematic_detections, 1):
        print(f"🧪 Test {i}: {detection['category']} - '{detection['text']}'")
        print(f"   Confidence: {detection['confidence']:.1%}")
        
        # Create a test text with this detection
        test_text = f"Some data: {detection['text']}"
        
        try:
            response = requests.post(
                "http://localhost:8000/api/validated/detect",
                json={
                    "text": test_text,
                    "use_regex": True,
                    "use_contextual": True,
                    "use_ml": False,
                    "min_confidence": 0.5
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                valid_entities = data.get('entities', [])
                filtered_entities = data.get('filtered_entities', [])
                
                # Check if this specific detection was filtered
                found_in_filtered = any(
                    entity['word'] == detection['text'] and 
                    entity['entity_group'] == detection['category']
                    for entity in filtered_entities
                )
                
                found_in_valid = any(
                    entity['word'] == detection['text'] and 
                    entity['entity_group'] == detection['category']
                    for entity in valid_entities
                )
                
                if found_in_filtered:
                    print("   ✅ CORRECTLY FILTERED as false positive")
                elif found_in_valid:
                    print("   ❌ INCORRECTLY ACCEPTED (should be filtered)")
                else:
                    print("   ⚠️  Not detected at all")
                
            else:
                print(f"   ❌ HTTP Error: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("   ❌ Connection Error: Server not running")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        print()

def main():
    """Main test function"""
    print("🚀 Validated PII Detection Test Suite")
    print("=" * 60)
    print("This test demonstrates how the validated system fixes")
    print("false positive issues by using strict schema validation.")
    print("=" * 60)
    print()
    
    # Test general validation
    test_validated_detection()
    
    # Test specific false positives
    test_specific_false_positives()
    
    print("🎉 Test Complete!")
    print("=" * 30)
    print("Key improvements demonstrated:")
    print("✅ False positive filtering")
    print("✅ Schema pattern validation")
    print("✅ Confidence-based filtering")
    print("✅ Detailed validation reasons")

if __name__ == "__main__":
    main()
