#!/usr/bin/env python3
"""
Amazon SP-API OAuth Token Generator

This script helps you obtain an initial refresh token for Amazon Selling Partner API.
It guides you through the OAuth 2.0 authorization flow and updates your .env file
with the obtained tokens.

Requirements:
- Python 3.6+
- Requests library
- python-dotenv library
"""

import os
import json
import time
import webbrowser
import http.server
import socketserver
import urllib.parse
import base64
import requests
from dotenv import load_dotenv, set_key

# Constants
AUTH_URL = "https://sellercentral.amazon.com/apps/authorize/consent"
TOKEN_URL = "https://api.amazon.com/auth/o2/token"
REDIRECT_URI = "http://localhost:8888/callback"
STATE = "state123"  # For CSRF protection
SP_API_ENV_FILE = ".env"

# Global variables
received_auth_code = None

class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Handler for the OAuth callback"""
    
    def do_GET(self):
        """Handle GET requests to the callback URL"""
        global received_auth_code
        
        # Parse the query parameters
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        # Check if we received an authorization code
        if 'code' in params:
            received_auth_code = params['code'][0]
            
            # Send a success response to the browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html_content = """
            <html>
            <head><title>Amazon SP-API Authorization Successful</title></head>
            <body>
                <h1>Authorization Successful!</h1>
                <p>You have successfully authorized the application. You can close this window now.</p>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
            
        else:
            # Send an error response
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html_content = """
            <html>
            <head><title>Amazon SP-API Authorization Failed</title></head>
            <body>
                <h1>Authorization Failed</h1>
                <p>Failed to receive an authorization code. Please try again.</p>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))

def load_api_credentials():
    """Load API credentials from the .env file"""
    load_dotenv(SP_API_ENV_FILE)
    
    # Get credentials from .env file
    client_id = os.getenv("AMAZON_CLIENT_ID")
    client_secret = os.getenv("AMAZON_CLIENT_SECRET")
    
    # Check if required credentials are available
    if not client_id or not client_secret:
        print("ERROR: Missing required credentials in .env file.")
        print("Make sure AMAZON_CLIENT_ID and AMAZON_CLIENT_SECRET are set.")
        return None, None
    
    return client_id, client_secret

def start_auth_server():
    """Start a local HTTP server to receive the OAuth callback"""
    # Parse the port from REDIRECT_URI
    port = int(REDIRECT_URI.split(':')[2].split('/')[0])
    
    # Create and start the server
    httpd = socketserver.TCPServer(("", port), OAuthCallbackHandler)
    print(f"Waiting for authorization on port {port}...")
    
    # Handle one request, then shut down
    httpd.handle_request()
    httpd.server_close()

def open_auth_page(client_id):
    """Open the Amazon authorization page in the default browser"""
    auth_params = {
        'application_id': client_id,
        'state': STATE,
        'version': 'beta',
        'redirect_uri': REDIRECT_URI
    }
    
    # Build the authorization URL
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    
    print(f"Opening browser to authorize the application: {auth_url}")
    webbrowser.open(auth_url)

def exchange_code_for_tokens(client_id, client_secret, auth_code):
    """
    Exchange the authorization code for refresh and access tokens
    
    Args:
        client_id (str): Your Amazon Client ID
        client_secret (str): Your Amazon Client Secret
        auth_code (str): The authorization code received from Amazon
    
    Returns:
        dict: Response containing the tokens
    """
    # Prepare the request headers
    auth_string = f"{client_id}:{client_secret}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}"
    }
    
    # Prepare the request body
    body = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI
    }
    
    try:
        # Make the request to Amazon's token endpoint
        response = requests.post(TOKEN_URL, headers=headers, data=body)
        response.raise_for_status()
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to exchange code for tokens: {str(e)}")
        if response:
            print(f"Response: {response.text}")
        return None

def update_env_file(token_data):
    """
    Update the .env file with the received tokens
    
    Args:
        token_data (dict): Token data from the authorization response
    """
    try:
        # Update tokens in the .env file
        if "access_token" in token_data:
            set_key(SP_API_ENV_FILE, "AMAZON_ACCESS_TOKEN", token_data["access_token"])
            
        if "refresh_token" in token_data:
            set_key(SP_API_ENV_FILE, "AMAZON_REFRESH_TOKEN", token_data["refresh_token"])
            
        return True
    except Exception as e:
        print(f"ERROR: Failed to update .env file: {str(e)}")
        return False

def main():
    """Main function to get SP API tokens"""
    print("Amazon SP-API OAuth Token Generator")
    print("----------------------------------")
    
    # Load credentials
    client_id, client_secret = load_api_credentials()
    if not client_id or not client_secret:
        return
    
    print(f"Client ID: {client_id[:5]}...{client_id[-5:]}")
    print("\nThis script will guide you through the Amazon SP-API authorization process.")
    print("It will open a browser window for you to authorize the application.")
    print("After authorization, the browser will redirect to a local server to capture the code.")
    print("\nMake sure you are logged into Seller Central before proceeding.")
    
    input("\nPress Enter to start the authorization process...")
    
    # Start the authorization server
    import threading
    server_thread = threading.Thread(target=start_auth_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Open the authorization page
    open_auth_page(client_id)
    
    # Wait for the authorization code
    timeout = 120  # seconds
    start_time = time.time()
    
    while received_auth_code is None:
        if time.time() - start_time > timeout:
            print("\nTimeout waiting for authorization. Please try again.")
            return
        time.sleep(1)
    
    # Exchange the authorization code for tokens
    print("\nReceived authorization code. Exchanging for tokens...")
    token_data = exchange_code_for_tokens(client_id, client_secret, received_auth_code)
    
    if not token_data:
        print("Failed to exchange code for tokens. Please try again.")
        return
    
    # Print token details (partial for security)
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", "Unknown")
    
    print(f"\nSuccess! Tokens received.")
    print(f"Access token expires in: {expires_in} seconds")
    print(f"Access token: {access_token[:10]}...{access_token[-10:] if len(access_token) > 20 else ''}")
    print(f"Refresh token: {refresh_token[:5]}...{refresh_token[-5:] if len(refresh_token) > 10 else ''}")
    
    # Update the .env file
    if update_env_file(token_data):
        print("\nThe .env file has been updated with the new tokens.")
        print("Your application can now authenticate with Amazon SP-API.")
    else:
        print("\nFailed to update the .env file. Please update it manually with the new tokens.")
        print(f"Access token: {access_token}")
        print(f"Refresh token: {refresh_token}")

if __name__ == "__main__":
    main() 