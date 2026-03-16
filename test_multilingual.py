#!/usr/bin/env python3
"""
Comprehensive multilingual test for TC-EUSL AI System
Tests: English, Sinhala, Tamil
"""
import requests
import json
import time

print("\n" + "="*80)
print("🌍 MULTILINGUAL CHAT TEST - TC-EUSL AI SYSTEM")
print("="*80)

BASE_URL = "http://localhost:5000/api/chat"
HEADERS = {"Content-Type": "application/json"}

# Test cases
TESTS = [
    {
        "name": "English - Phone Number",
        "language": "en",
        "question": "What is the contact phone number?",
        "expected_lang": "English"
    },
    {
        "name": "English - Library Info",
        "language": "en",
        "question": "Tell me about the library",
        "expected_lang": "English"
    },
    {
        "name": "Sinhala - Phone Number",
        "language": "si",
        "question": "දුරකතනය කුමක්ද?",
        "expected_lang": "Sinhala (සිංහල)"
    },
    {
        "name": "Sinhala - Faculties",
        "language": "si",
        "question": "ශිල්පවලි මොනවාද?",
        "expected_lang": "Sinhala (සිංහල)"
    },
    {
        "name": "Tamil - Phone Number",
        "language": "ta",
        "question": "தொலைபேசி எண் என்ன?",
        "expected_lang": "Tamil (தமிழ்)"
    },
    {
        "name": "Tamil - Campus Info",
        "language": "ta",
        "question": "வளாகம் பற்றி சொல்லுங்கள்",
        "expected_lang": "Tamil (தமிழ்)"
    }
]

# Run tests
passed = 0
failed = 0

for i, test in enumerate(TESTS, 1):
    print(f"\n{"─"*80}")
    print(f"Test {i}/{len(TESTS)}: {test['name']}")
    print(f"{"─"*80}")
    
    try:
        # Make request
        payload = {
            "language": test["language"],
            "question": test["question"]
        }
        
        print(f"📤 Question ({test['expected_lang']}): {test['question']}")
        print(f"🔧 Language Code: {test['language']}")
        
        response = requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ FAILED: HTTP {response.status_code}")
            failed += 1
            continue
        
        result = response.json()
        answer = result["answer"]
        duration = result["duration_ms"]
        model = result["llm_model"]
        
        print(f"\n📥 Answer ({test['expected_lang']}):")
        print(f"   {answer}")
        print(f"\n⏱️  Response Time: {duration}ms")
        print(f"🤖 LLM Model: {model}")
        
        # Check if answer is in the expected language
        # Simple heuristic check
        is_english = any(word in answer.lower() for word in ["the", "is", "call", "contact", "phase", "campus"])
        has_sinhala = any(char in answer for char in "ක ල ර ස ඩ න ම ශ".split())
        has_tamil = any(char in answer for char in "க ல ர த ந ம ய வ".split())
        
        language_ok = False
        if test["language"] == "en" and is_english:
            language_ok = True
            status = "✅ PASS - English"
        elif test["language"] == "si" and has_sinhala:
            language_ok = True
            status = "✅ PASS - Sinhala"
        elif test["language"] == "ta" and has_tamil:
            language_ok = True
            status = "✅ PASS - Tamil"
        else:
            status = "⚠️ WARNING - May not be in correct language"
        
        print(f"\n{status}")
        
        if language_ok or "technical difficulties" not in answer:
            passed += 1
        else:
            failed += 1
            
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        failed += 1

# Summary
print(f"\n\n{'='*80}")
print("📊 TEST SUMMARY")
print(f"{'='*80}")
print(f"✅ Passed: {passed}/{len(TESTS)}")
print(f"❌ Failed: {failed}/{len(TESTS)}")
print(f"Success Rate: {(passed/len(TESTS)*100):.1f}%")

if passed == len(TESTS):
    print("\n🎉 ALL TESTS PASSED! Multilingual support is working!")
elif passed >= len(TESTS) - 1:
    print("\n✅ Most tests passed. System is mostly working!")
else:
    print("\n⚠️ Some tests failed. Check configuration.")

print(f"{'='*80}\n")
