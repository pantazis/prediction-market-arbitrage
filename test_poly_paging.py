import requests
import json

def test_pagination():
    url = "https://gamma-api.polymarket.com/markets"
    
    # 1. Fetch first page
    params1 = {
        "active": "true",
        "closed": "false",
        "limit": 10,
        "offset": 0,
        "order": "volume24hr",
        "ascending": "false"
    }
    resp1 = requests.get(url, params=params1)
    data1 = resp1.json()
    markets1 = data1 if isinstance(data1, list) else data1.get("data", [])
    
    # 2. Fetch second page
    params2 = {
        "active": "true",
        "closed": "false",
        "limit": 10,
        "offset": 10,
        "order": "volume24hr",
        "ascending": "false"
    }
    resp2 = requests.get(url, params=params2)
    data2 = resp2.json()
    markets2 = data2 if isinstance(data2, list) else data2.get("data", [])
    
    print(f"Page 1 first ID: {markets1[0].get('id')}")
    print(f"Page 2 first ID: {markets2[0].get('id')}")
    
    if markets1[0].get('id') != markets2[0].get('id'):
        print("SUCCESS: Offset parameter works (IDs are different).")
    else:
        print("FAILURE: Offset parameter ignored (IDs are same).")

if __name__ == "__main__":
    test_pagination()
