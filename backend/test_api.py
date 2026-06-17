import requests

def test_url(name, url):
    print(f"Testing {name}: {url}")
    try:
        response = requests.post(url, json={'username': 'admin', 'password': '123'})
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 20)

# 1. Direct Backend
test_url("Backend Login", "http://127.0.0.1:5000/api/auth/login")

# 2. Backend Cases (Note trailing slash)
try:
    r = requests.get("http://127.0.0.1:5000/api/cases/")
    print(f"Testing Cases: {r.status_code}")
except:
    pass

# 3. Root (Should be 404 or verify Flask is running)
try:
    r = requests.get("http://127.0.0.1:5000/")
    print(f"Testing Root: {r.status_code}")
except:
    pass
