# E-commerce Agent Team

An AI-powered e-commerce assistant built with Streamlit that uses multiple specialized agents to help users with their e-commerce needs.

## Features

- Chat interface for interacting with AI agents
- Lead agent that processes user queries and delegates to specialized agents
- Product recommendation agent with sample product data
- Conversation history storage in SQLite database
- Searchable conversation history page
- Example queries for easy testing

## Setup Instructions

1. Clone this repository
2. Create a virtual environment:
   ```
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Create a `.env` file based on the `env.sample` template and add your API keys
6. Run the application:
   ```
   streamlit run app.py
   ```

## Project Structure

- `app.py` - Main Streamlit application with the chat interface
- `pages/` - Additional Streamlit pages
  - `01_History.py` - Page for viewing and searching conversation history
- `agents/` - Contains agent implementations
  - `lead_agent.py` - Main agent that handles user queries and delegates to specialized agents
  - `product_agent.py` - Specialized agent for product recommendations
- `database/` - Database handling code
  - `conversation_store.py` - Manages conversation history storage in SQLite

## How It Works

1. The Lead Agent receives user queries via the Streamlit chat interface
2. It analyzes the query intent to determine if it's about product recommendations, product info, or general e-commerce questions
3. Based on the intent, it delegates to specialized agents or handles the query directly
4. The Product Agent provides product recommendations using sample product data
5. All conversations are stored in a SQLite database and can be viewed in the History page

## API Keys Required

To use this application, you need to obtain the following API keys:

1. OpenAI API key - Required for the AI agents to function
2. (Optional) Amazon SP API credentials - For future integration with Amazon product data
3. (Optional) Rainforest API key - For future integration with product data from multiple retailers

## Next Steps for Development

1. Implement additional specialized agents for different e-commerce tasks
2. Add real product search and recommendation capabilities using e-commerce APIs
3. Integrate with e-commerce platforms (Amazon, Shopify, etc.)
4. Enhance the user interface with product cards and images
5. Add user authentication and personalized recommendations 