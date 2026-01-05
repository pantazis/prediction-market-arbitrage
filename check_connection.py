import requests
import urllib3

# Disable warnings for SSL bypass if needed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_connection():
    url = "https://clob.polymarket.com/time"
    print(f"Testing connection to: {url}")
    
    try:
        # We try without verify=False first to see if SSL works (if VPN handles it)
        # If that fails, we can add verify=False logic, but for now standard check.
        # Actually, let's use verify=False to rule out SSL issues and focus on the HTTP 451/200 status.
        resp = requests.get(url, verify=False, timeout=10)
        
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            print("✅ Connection SUCCESSFUL! You can access Polymarket.")
        elif resp.status_code == 451:
            print("❌ Connection BLOCKED (Legal Reasons/Geoblock).")
            print("The Hellenic Gaming Commission or your ISP is blocking this site.")
            print("You need a VPN enabled to proceed.")
        elif resp.status_code == 403:
            print("❌ Connection FORBIDDEN (403). Possible Cloudflare block or IP ban.")
        else:
            print(f"⚠️ Unexpected Status: {resp.status_code}")
            print(resp.text[:200])
            
    except Exception as e:
        print(f"❌ Connection FAILED: {e}")

if __name__ == "__main__":
    check_connection()
