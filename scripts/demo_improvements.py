#!/usr/bin/env python3
"""
Demo of PII Detection Improvements
Shows the key enhancements made to address missed PII detection
"""

import re
import json

def demo_contextual_detection():
    """Demonstrate contextual PII detection improvements"""
    print("🔍 Contextual PII Detection Demo")
    print("=" * 50)
    
    # Contextual patterns that address the schema gaps
    contextual_patterns = {
        'FULLNAME': [
            r'(?:name|Name|NAME)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'(?:customer|Customer|CUSTOMER)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'(?:contact|Contact|CONTACT)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)'
        ],
        'EMAIL': [
            r'(?:email|Email|EMAIL)\s*:?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
        ],
        'TELEPHONENUM': [
            r'(?:phone|Phone|PHONE|mobile|Mobile|MOBILE)\s*:?\s*((?:\+91[-\\s]?|0)?[6789]\\d{9})'
        ],
        'PASSPORTNUM': [
            r'(?:passport|Passport|PASSPORT|passport\s*number|Passport\s*Number)\s*:?\s*([A-Z]\\d{7})'
        ],
        'PAN': [
            r'(?:pan|PAN|pan\s*number|PAN\s*Number)\s*:?\s*([A-Z]{3}[PFCHAT][A-Z]\\d{4}[A-Z])'
        ],
        'AADHAAR': [
            r'(?:aadhaar|Aadhaar|AADHAAR|aadhar|Aadhar|AADHAR)\s*:?\s*(\\d{4}\\s\\d{4}\\s\\d{4})'
        ],
        'ACCOUNTNUM': [
            r'(?:account|Account|ACCOUNT|account\s*number|Account\s*Number)\s*:?\s*(\\d{9,18})'
        ],
        'IFSC': [
            r'(?:ifsc|IFSC|ifsc\s*code|IFSC\s*Code)\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})'
        ],
        'CREDITCARDNUM': [
            r'(?:credit\s*card|Credit\s*Card|CREDIT\s*CARD|card\s*number|Card\s*Number)\s*:?\s*(\\d{4}\\s\\d{4}\\s\\d{4}\\s\\d{4})'
        ],
        'TRANSACTIONID': [
            r'(?:transaction|Transaction|TRANSACTION|txn|TXN|transaction\s*id|Transaction\s*ID)\s*:?\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})'
        ],
        'AGE': [
            r'(?:age|Age|AGE)\s*:?\s*(\\d{1,3})'
        ],
        'GENDER': [
            r'(?:gender|Gender|GENDER|sex|Sex|SEX)\s*:?\s*(M|F|Male|Female|MALE|FEMALE)'
        ],
        'DATE': [
            r'(?:dob|DOB|date|Date|DATE|birth|Birth|BIRTH)\s*:?\s*(\\d{2}[-/]\\d{2}[-/]\\d{4})'
        ],
        'CITY': [
            r'(?:city|City|CITY)\s*:?\s*([A-Za-z\\s]+)'
        ],
        'ZIPCODE': [
            r'(?:pincode|Pincode|PINCODE|zip|Zip|ZIP)\s*:?\s*(\\d{6})'
        ]
    }
    
    # Test cases that were problematic for the original models
    test_cases = [
        "Name: Arun Sharma, Email: arun.sharma@hdfc.com, Phone: +91-9876543210",
        "Customer: Priya Mehta, Age: 28, Gender: Female, DOB: 15/08/1995",
        "PAN Number: AAAPA1234A, Aadhaar: 1234 5678 9012, Passport: K1234567",
        "Account Number: 123456789, IFSC Code: HDFC0001234, Credit Card: 4111 1111 1111 1111",
        "Transaction ID: f47ac10b-58cc-4372-a567-0e02b2c3d479, City: Mumbai, Pincode: 400001"
    ]
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n📝 Test Case {i}: {test_text}")
        print("-" * 40)
        
        detected_entities = []
        
        for category, patterns in contextual_patterns.items():
            for pattern in patterns:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    for match in compiled.finditer(test_text):
                        detected_entities.append({
                            'category': category,
                            'text': match.group(1),
                            'start': match.start(1),
                            'end': match.end(1),
                            'method': 'contextual'
                        })
                except Exception as e:
                    continue
        
        if detected_entities:
            print(f"✅ Detected {len(detected_entities)} entities:")
            for entity in detected_entities:
                print(f"  - {entity['category']}: '{entity['text']}' (pos: {entity['start']}-{entity['end']})")
        else:
            print("❌ No entities detected")

def demo_improved_name_detection():
    """Demonstrate improved name detection"""
    print("\n\n👤 Improved Name Detection Demo")
    print("=" * 50)
    
    # Patterns specifically designed to address the low F1 scores for names
    name_patterns = {
        'FULLNAME': [
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # Basic full name
            r'(?:name|Name|NAME)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Contextual
            r'(?:customer|Customer|CUSTOMER)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Customer context
        ],
        'INDIAN_NAMES': [
            r'\b[A-Z][a-z]+\s+(?:Kumar|Singh|Sharma|Verma|Mehta|Patel|Gupta|Agarwal|Jain|Shah)\b',  # Common Indian surnames
            r'\b(?:Ravi|Arun|Priya|Neha|Deepak|Sunil|Raj|Amit|Suresh|Kavita)\s+[A-Z][a-z]+\b',  # Common Indian first names
        ]
    }
    
    test_names = [
        "My name is Arun Sharma",
        "Customer: Priya Mehta", 
        "Contact person: Ravi Kumar Singh",
        "Name: Neha Agarwal",
        "Deepak Verma is the account holder",
        "Sunil Kumar Patel and Kavita Sharma are colleagues"
    ]
    
    for test_text in test_names:
        print(f"\n📝 Testing: {test_text}")
        
        detected = []
        for category, patterns in name_patterns.items():
            for pattern in patterns:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    for match in compiled.finditer(test_text):
                        detected.append({
                            'category': category,
                            'text': match.group() if match.groups() == () else match.group(1),
                            'start': match.start(),
                            'end': match.end()
                        })
                except Exception as e:
                    continue
        
        if detected:
            detected_str = [f"{d['category']}: '{d['text']}'" for d in detected]
            print(f"✅ Detected: {detected_str}")
        else:
            print("❌ No names detected")

def demo_missing_pasport_detection():
    """Demonstrate the newly added PASSPORTNUM detection"""
    print("\n\n🛂 Missing PASSPORTNUM Detection Demo")
    print("=" * 50)
    
    # This was completely missing from the original models (F1=0.0)
    passport_patterns = [
        r'\b[A-Z]\d{7}\b',  # Basic pattern
        r'(?:passport|Passport|PASSPORT|passport\s*number|Passport\s*Number)\s*:?\s*([A-Z]\d{7})',  # Contextual
        r'(?:travel\s*document|Travel\s*Document|TRAVEL\s*DOCUMENT)\s*:?\s*([A-Z]\d{7})',  # Alternative context
    ]
    
    test_passports = [
        "Passport: K1234567",
        "Passport Number: Z7654321", 
        "Travel document: A9876543",
        "PASSPORT: B1234567",
        "Travel Document: C5555555"
    ]
    
    for test_text in test_passports:
        print(f"\n📝 Testing: {test_text}")
        
        detected = []
        for pattern in passport_patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                for match in compiled.finditer(test_text):
                    detected.append({
                        'text': match.group() if match.groups() == () else match.group(1),
                        'start': match.start(),
                        'end': match.end()
                    })
            except Exception as e:
                continue
        
        if detected:
            detected_str = [f"'{d['text']}'" for d in detected]
            print(f"✅ Detected: {detected_str}")
        else:
            print("❌ No passport numbers detected")

def demo_comprehensive_improvements():
    """Show comprehensive improvements addressing all schema categories"""
    print("\n\n🎯 Comprehensive PII Detection Improvements")
    print("=" * 50)
    
    # Load the original schema to show we're covering all categories
    try:
        with open("data_schema.json", 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        print(f"📋 Schema Categories: {list(schema.keys())}")
        print(f"📊 Total Categories: {len(schema)}")
        
        # Show which categories had issues in the original models
        problematic_categories = {
            'FULLNAME': 'F1=0.20-0.43 (very low)',
            'GIVENNAME': 'F1=0.28-0.46 (low)', 
            'SURNAME': 'F1=0.08-0.12 (very low)',
            'PASSPORTNUM': 'F1=0.0 (missing)',
            'ZIPCODE': 'F1=0.73 (moderate)',
            'CITY': 'F1=0.77 (moderate)'
        }
        
        print(f"\n⚠️  Problematic Categories in Original Models:")
        for category, issue in problematic_categories.items():
            print(f"  - {category}: {issue}")
        
        print(f"\n✅ Improvements Implemented:")
        print(f"  - Enhanced contextual detection for all categories")
        print(f"  - Added missing PASSPORTNUM detection")
        print(f"  - Improved name detection with Indian-specific patterns")
        print(f"  - Multi-method detection combining regex + ML models")
        print(f"  - Configurable confidence thresholds")
        print(f"  - Better false positive reduction")
        
    except FileNotFoundError:
        print("❌ Schema file not found")

def main():
    """Run all demonstration functions"""
    print("🚀 PII Detection Improvements Demonstration")
    print("=" * 60)
    print("This demo shows the key improvements made to address")
    print("missed PII detection based on the data_schema.json analysis.")
    print("=" * 60)
    
    # Run all demos
    demo_contextual_detection()
    demo_improved_name_detection() 
    demo_missing_pasport_detection()
    demo_comprehensive_improvements()
    
    print("\n\n🎉 Demo Complete!")
    print("=" * 30)
    print("Key improvements demonstrated:")
    print("✅ Contextual PII detection")
    print("✅ Enhanced name detection")
    print("✅ Missing PASSPORTNUM support")
    print("✅ Comprehensive category coverage")
    print("\nThese improvements address the major gaps identified")
    print("in the original BERT and LLaMA model evaluations.")

if __name__ == "__main__":
    main()
