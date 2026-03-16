import requests
import json
import time

print("=" * 60)
print("Testing Chat Endpoint")
print("=" * 60)
time.sleep(1)

url = "http://localhost:5000/api/chat"
data = {"language": "en", "question": "What is the contact phone number?"}
headers = {"Content-Type": "application/json"}

try:
    print(f"\n📤 Sending: {data['question']}")
    r = requests.post(url, json=data, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    
    result = r.json()
    print(f"\n✅ Answer: {result['answer']}")
    print(f"⏱️  Duration: {result['duration_ms']}ms")
    print(f"🔧 Source: {result['llm_source']}")
    print(f"📊 Model: {result['llm_model']}")
    
    # Check if it's the error response
    if "technical difficulties" in result['answer']:
        print("\n❌ ERROR: Still getting error response. Checking logs...")
    else:
        print("\n✅ SUCCESS: Chat is working!")
        
except Exception as e:
    print(f"❌ Error: {e}")
