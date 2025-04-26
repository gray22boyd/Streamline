#!/usr/bin/env python3
"""
Amazon SP-API Token Refresh Script

This script refreshes your Amazon Selling Partner API access token using the OAuth 2.0 
refresh token flow. When run, it will fetch a new access token and update your .env file.

Requirements:
- Python 3.6+
- Requests library
- python-dotenv library
"""

import os
import json
import base64
import requests
from dotenv import load_dotenv, set_key

# Constants
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_ENV_FILE = ".env"

def load_api_credentials():
    """Load API credentials from the .env file"""
    load_dotenv(SP_API_ENV_FILE)
    
    # Get credentials from .env file
    client_id = os.getenv("AMAZON_CLIENT_ID")
    client_secret = os.getenv("AMAZON_CLIENT_SECRET")
    refresh_token = os.getenv("AMAZON_REFRESH_TOKEN")
    
    # Check if all required credentials are available
    if not client_id or not client_secret:
        print("ERROR: Missing required credentials in .env file.")
        print("Make sure AMAZON_CLIENT_ID and AMAZON_CLIENT_SECRET are set.")
        return None, None, None
        
    # If no refresh token is found, we'll go with what we have
    if not refresh_token:
        print("WARNING: No refresh token found in .env file. You may need to complete the OAuth flow first.")
    
    return client_id, client_secret, refresh_token

def refresh_access_token(client_id, client_secret, refresh_token=None):
    """
    Refresh Amazon SP API access token
    
    Args:
        client_id (str): Your Amazon Client ID
        client_secret (str): Your Amazon Client Secret
        refresh_token (str, optional): Refresh token. If not provided, we'll attempt a client credentials flow
        
    Returns:
        dict: Response containing the new access token and expiration details
    """
    # Prepare authorization header (Basic auth using client_id:client_secret)
    auth_string = f"{client_id}:{client_secret}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    
    # Prepare the request body based on whether we have a refresh token
    if refresh_token:
        # Use refresh token grant type if refresh token is available
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
    else:
        # Fall back to client credentials flow if no refresh token
        body = {
            "grant_type": "client_credentials",
            "scope": "sellingpartnerapi::notifications"  # Basic scope for testing
        }
    
    try:
        # Make the request to Amazon's token endpoint
        response = requests.post(LWA_TOKEN_URL, headers=headers, data=body)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse and return the JSON response
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to refresh token: {str(e)}")
        if response:
            print(f"Response: {response.text}")
        return None

def update_env_file(token_data):
    """
    Update the .env file with the new access token
    
    Args:
        token_data (dict): Token data from the refresh response
    """
    # Extract the new access token
    access_token = token_data.get("access_token")
    
    if not access_token:
        print("ERROR: No access token found in the response.")
        return False
    
    try:
        # Update the .env file with the new access token
        set_key(SP_API_ENV_FILE, "AMAZON_ACCESS_TOKEN", access_token)
        
        # Also save refresh token if provided in the response
        if "refresh_token" in token_data:
            set_key(SP_API_ENV_FILE, "AMAZON_REFRESH_TOKEN", token_data["refresh_token"])
        
        return True
    except Exception as e:
        print(f"ERROR: Failed to update .env file: {str(e)}")
        return False

def main():
    """Main function to refresh SP API token"""
    print("Amazon SP-API Token Refresh Utility")
    print("-----------------------------------")
    
    # Load credentials
    client_id, client_secret, refresh_token = load_api_credentials()
    if not client_id or not client_secret:
        return
    
    print(f"Client ID: {client_id[:5]}...{client_id[-5:]}")
    print(f"Refresh Token: {'Available' if refresh_token else 'Not available'}")
    
    # Refresh the token
    print("\nRefreshing access token...")
    token_data = refresh_access_token(client_id, client_secret, refresh_token)
    
    if not token_data:
        print("Failed to refresh token. Please check your credentials and network connection.")
        return
    
    # Print token details (partial for security)
    access_token = token_data.get("access_token", "")
    expires_in = token_data.get("expires_in", "Unknown")
    token_type = token_data.get("token_type", "Unknown")
    
    print(f"Success! New access token received.")
    print(f"Token type: {token_type}")
    print(f"Expires in: {expires_in} seconds")
    print(f"Access token: {access_token[:10]}...{access_token[-10:]}")
    
    # Update the .env file
    if update_env_file(token_data):
        print("\nThe .env file has been updated with the new access token.")
        print("Your application should now be able to authenticate with Amazon SP-API.")
    else:
        print("\nFailed to update the .env file. Please update it manually with the new access token.")
        print(f"Access token: {access_token}")

if __name__ == "__main__":
    main() 