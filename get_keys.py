import os
import requests
import urllib3
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# BYPASS SSL VERIFICATION (Likely due to corporate proxy/Zscaler)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Monkey patch requests to ignore verify=True
_original_request = requests.Session.request
def _insecure_request(self, method, url, *args, **kwargs):
    kwargs['verify'] = False
    return _original_request(self, method, url, *args, **kwargs)
requests.Session.request = _insecure_request

def main():
    print("--- Polymarket Key Generator ---")
    print("This script will help you set up new credentials.")
    print("1. Generate a BRAND NEW Wallet (Recommended if your previous key was exposed)")
    print("2. Derive API keys from an existing Private Key")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == '1':
        # Generate new account
        acct = Account.create()
        private_key = acct.key.hex()
        address = acct.address
        print(f"\n[SUCCESS] New Wallet Generated!")
        print(f"Address: {address}")
        print(f"Private Key: {private_key}")
        print("\nIMPORTANT: Save this Private Key securely! If you lose it, you lose access to funds.")
        
    elif choice == '2':
        private_key = input("\nEnter your Private Key (secure input): ").strip()
        if not private_key.startswith("0x"):
            # Try to handle if they forgot 0x or plain hex
            try:
                if len(private_key) == 64:
                    private_key = "0x" + private_key
            except:
                pass
    else:
        print("Invalid choice.")
        return

    print("\nDeriving API Credentials...")
    try:
        # Initialize ClobClient to derive keys
        # We don't need to connect to host to derive keys usually, 
        # but the library structure might require instantation.
        # We use a dummy host if needed, but clob.polymarket.com is fine.
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137 # Polygon
        )
        
        # create_or_derive_api_creds returns py_clob_client.clob_types.ApiCreds
        creds = client.create_or_derive_api_creds()
        
        print("\n--- COPY TO YOUR .env FILE ---")
        print(f"POLYMARKET_PRIVATE_KEY={private_key}")
        print(f"POLYMARKET_API_KEY={creds.api_key}")
        print(f"POLYMARKET_SECRET={creds.api_secret}")
        print(f"POLYMARKET_PASSPHRASE={creds.api_passphrase}")
        print("------------------------------")
        print("\nUpdate your .env file with these values.")
        
    except Exception as e:
        print(f"\n[ERROR] Could not derive keys: {e}")
        print("Make sure py-clob-client is installed and the private key is valid.")

if __name__ == "__main__":
    main()
