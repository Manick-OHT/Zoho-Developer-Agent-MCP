"""
Zoho OAuth Token Exchange Script
================================
Run this script to exchange a grant code for a refresh token.

Usage:
  1. Go to https://api-console.zoho.com
  2. Click your Self Client
  3. Generate a code with these scopes:
     ZohoCreator.meta.READ,ZohoCreator.data.READ,ZohoCreator.data.CREATE,ZohoCreator.form.CREATE,ZohoCreator.report.READ
  4. Run: python get_token.py <grant_code>
  5. Copy the refresh_token to your .env file
"""

import sys
import requests
from dotenv import load_dotenv
import os

load_dotenv()


def exchange_code(grant_code: str):
    client_id = os.getenv("ZOHO_CLIENT_ID", "")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET", "")
    accounts_domain = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "accounts.zoho.com")

    if not client_id or not client_secret:
        print("❌ Error: ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET must be set in .env")
        return

    # Try multiple domains
    domains = [accounts_domain, "accounts.zoho.com", "accounts.zoho.in", "accounts.zoho.eu"]
    # Remove duplicates while preserving order
    seen = set()
    unique_domains = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            unique_domains.append(d)

    for domain in unique_domains:
        print(f"\n🔄 Trying domain: {domain}...")
        url = f"https://{domain}/oauth/v2/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": grant_code,
        }

        try:
            resp = requests.post(url, data=data, timeout=15)
            result = resp.json()

            if "access_token" in result:
                print(f"\n✅ SUCCESS on domain: {domain}")
                print(f"\n📋 Access Token: {result['access_token'][:50]}...")
                print(f"📋 Refresh Token: {result.get('refresh_token', 'N/A')}")
                print(f"⏱️  Expires In: {result.get('expires_in', 'N/A')} seconds")
                print(f"\n{'='*60}")
                print(f"Add these to your .env file:")
                print(f"{'='*60}")
                print(f"ZOHO_REFRESH_TOKEN={result.get('refresh_token', '')}")
                print(f"ZOHO_ACCOUNTS_DOMAIN={domain}")
                print(f"ZOHO_CREATOR_DOMAIN={domain.replace('accounts.', 'creator.')}")
                return result
            else:
                print(f"   ❌ Error: {result.get('error', 'unknown')}")
        except Exception as e:
            print(f"   ❌ Request failed: {e}")

    print("\n❌ Could not exchange the code on any domain.")
    print("   Please verify your Client ID and Client Secret are correct.")
    print("   Also make sure the grant code hasn't expired (10 min validity).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_token.py <grant_code>")
        print("\nGenerate a grant code at https://api-console.zoho.com")
        sys.exit(1)

    code = sys.argv[1]
    print(f"🔑 Exchanging grant code: {code[:20]}...")
    exchange_code(code)
