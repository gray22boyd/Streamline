import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key
api_key = os.getenv("OPENAI_API_KEY")
print(f"API Key found: {'Yes' if api_key else 'No'}")
print(f"API Key starts with: {api_key[:12]}...")

try:
    # Initialize the OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Make a request
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    
    print("Connection successful!")
    print(f"Response: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"Connection error: {type(e).__name__}: {e}") 