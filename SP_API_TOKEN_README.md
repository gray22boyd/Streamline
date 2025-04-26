# Amazon SP-API Token Management

This directory contains scripts to help you manage your Amazon Selling Partner API tokens. The Amazon SP-API requires OAuth 2.0 for authentication, and access tokens expire regularly, requiring you to refresh them.

## Scripts Included

1. **get_sp_api_tokens.py** - Helps you obtain an initial refresh token through the OAuth 2.0 authorization flow
2. **refresh_sp_api_token.py** - Refreshes your access token using the long-lived refresh token

## Prerequisites

Before using these scripts, make sure you have:

1. An Amazon Seller Central account
2. A registered SP-API application with client ID and client secret
3. Python 3.6 or higher
4. The following Python packages installed:
   - requests
   - python-dotenv

You can install the required packages using:

```bash
pip install requests python-dotenv
```

## Step 1: Initial Setup (One-time Process)

To set up the SP-API tokens initially, you need to:

1. Run the `get_sp_api_tokens.py` script which will:
   - Open a browser window to authenticate with Amazon
   - Get a refresh token and access token
   - Update your `.env` file with these tokens

```bash
python3 get_sp_api_tokens.py
```

This script will require you to log in to your Amazon Seller Central account and authorize your application.

## Step 2: Refreshing Access Tokens (Periodic Process)

Access tokens expire after a certain period (typically 1 hour). Whenever you need a new access token:

1. Run the `refresh_sp_api_token.py` script which will:
   - Use your existing refresh token to get a new access token
   - Update your `.env` file with the new access token

```bash
python3 refresh_sp_api_token.py
```

## Troubleshooting

### 1. "The access token you provided has expired"

If you see this error in your application, it means your access token has expired. Run the refresh script:

```bash
python3 refresh_sp_api_token.py
```

### 2. "refresh_token is missing"

If you don't have a refresh token:

1. Make sure you've run the `get_sp_api_tokens.py` script first
2. Check your `.env` file to ensure the `AMAZON_REFRESH_TOKEN` field is populated

### 3. Authorization Issues

If you're having trouble with the authorization process:

1. Make sure you're logged into the correct Seller Central account
2. Verify that your application is properly registered in Seller Central
3. Check that your client ID and client secret in the `.env` file are correct

## Security Note

These scripts handle sensitive authentication tokens. Always keep your:
- Client ID
- Client Secret
- Refresh Token
- Access Token

secure and never commit them to version control systems. The `.env` file should be included in your `.gitignore` file. 