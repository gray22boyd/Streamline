import streamlit as st
import os
import json
import sqlite3
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="E-commerce Agent Team",
    page_icon="🤖",
    layout="wide"
)

# Initialize OpenAI API
def get_openai_client():
    api_key = st.secrets["openai"]["api_key"] if "openai" in st.secrets else os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("No OpenAI API key found. Please set the OPENAI_API_KEY in your environment variables or Streamlit secrets.")
        st.stop()
    return OpenAI(api_key=api_key)

# Database setup
class ConversationStore:
    """Handles storage and retrieval of conversation history and products using SQLite."""
    
    def __init__(self, db_path='conversations.db'):
        """Initialize the conversation store with a database path"""
        # For Streamlit Cloud, use a path in the mounted filesystem or temporary directory
        if 'STREAMLIT_RUNTIME_ROOT' in os.environ:
            try:
                import tempfile
                temp_dir = tempfile.gettempdir()
                self.db_path = os.path.join(temp_dir, db_path)
                st.info(f"Using temporary directory for database: {self.db_path}")
            except Exception as e:
                self.db_path = db_path
                st.warning(f"Using default path for database: {self.db_path}")
        else:
            self.db_path = db_path
        
        # Create directory if needed
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        self._initialize_db()
    
    def _initialize_db(self):
        """Create the database and tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create conversations table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT NOT NULL,
            assistant_response TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_conversation(self, user_input, assistant_response, timestamp=None):
        """Save a conversation exchange to the database"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Convert timestamp to ISO format string
        timestamp_str = timestamp.isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO conversations (user_input, assistant_response, timestamp) VALUES (?, ?, ?)",
            (user_input, assistant_response, timestamp_str)
        )
        
        conn.commit()
        conn.close()
        
        return cursor.lastrowid

# Simple product recommendations
def get_product_recommendations(query, num_results=5):
    """Get sample product recommendations"""
    client = get_openai_client()
    
    # Generate a list of sample products based on the query
    products = []
    
    # Sample categories based on common query terms
    category = "General"
    if "headphone" in query.lower() or "audio" in query.lower():
        category = "Electronics"
    elif "water bottle" in query.lower() or "drink" in query.lower():
        category = "Kitchen"
    elif "shirt" in query.lower() or "clothing" in query.lower():
        category = "Apparel"
    elif "beauty" in query.lower() or "makeup" in query.lower():
        category = "Beauty"
    elif "bathroom" in query.lower():
        category = "Home"
    
    # Generate sample products with realistic data
    for i in range(num_results):
        # Use OpenAI to generate product titles based on the query
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You generate creative product names."},
                    {"role": "user", "content": f"Generate a realistic product title for a {category} product related to '{query}'. Don't use quotes. Keep it under 10 words."}
                ],
                max_tokens=30,
                temperature=0.7
            )
            title = response.choices[0].message.content.strip()
        except Exception as e:
            # Fallback titles if OpenAI fails
            fallback_titles = [
                f"Premium {category} Item #{i+1}",
                f"High-Quality {category} Product #{i+1}",
                f"Best-Selling {category} Solution #{i+1}",
                f"Professional {category} Tool #{i+1}",
                f"Innovative {category} Design #{i+1}"
            ]
            title = fallback_titles[i % len(fallback_titles)]
        
        # Generate realistic data for the product
        price = round(20 + (i * 15) + (hash(title) % 20), 2)  # Between $20-$100
        wholesale_price = round(price * 0.55, 2)  # 55% of retail
        profit_margin = round(((price - wholesale_price) / price) * 100, 2)
        rating = round(3.5 + (hash(title) % 15) / 10, 1)  # Between 3.5-5.0
        review_count = 50 + (hash(title[:5]) % 950)  # Between 50-1000
        asin = f"B{str(hash(title) % 100000000).zfill(8)}"[:10]
        
        # Add the product to the list
        products.append({
            "asin": asin,
            "title": title,
            "brand": f"{category} Brand {chr(65 + i)}",
            "price": price,
            "wholesale_price": wholesale_price,
            "profit_margin": profit_margin,
            "rating": rating,
            "review_count": review_count,
            "score": round(70 + (hash(title) % 30), 1),  # Between 70-100
        })
    
    return products

def format_product_recommendations(query, products):
    """Format product recommendations into a readable response"""
    if not products:
        return "I couldn't find any products matching your query. Could you try a different search?"
    
    response = f"Based on your search for '{query}', here are the top products:\n\n"
    
    for i, product in enumerate(products, 1):
        # Get product details
        title = product.get('title', 'Unknown Product')
        brand = product.get('brand', 'Unknown Brand')
        retail_price = product.get('price', 0)
        wholesale_price = product.get('wholesale_price', 0)
        rating = product.get('rating', 0)
        review_count = product.get('review_count', 0)
        profit_margin = product.get('profit_margin', 0)
        score = product.get('score', 0)
        
        # Format the product information
        response += f"**Product #{i} - Score: {score}/100**\n"
        response += f"- **Title:** {title}\n"
        response += f"- **Brand:** {brand}\n"
        response += f"- **Retail Price:** ${retail_price:.2f}\n"
        response += f"- **Wholesale Price:** ${wholesale_price:.2f}\n"
        response += f"- **Profit Margin:** {profit_margin:.2f}%\n"
        response += f"- **Rating:** {rating}/5 ({review_count} reviews)\n\n"
    
    response += "Would you like more detailed information about any of these products? Reply with 'analyze product #1' (or any number) for a detailed analysis."
    return response

def analyze_product(product):
    """Provide a simple analysis of a product"""
    title = product.get('title', 'Unknown Product')
    score = product.get('score', 0)
    price = product.get('price', 0)
    profit_margin = product.get('profit_margin', 0)
    
    analysis = f"# Product Analysis: {title}\n\n"
    analysis += f"## Overall Score: {score}/100\n\n"
    analysis += f"- Retail Price: ${price:.2f}\n"
    analysis += f"- Profit Margin: {profit_margin:.2f}%\n\n"
    
    if score > 80:
        analysis += "This product has excellent potential for e-commerce sellers."
    elif score > 60:
        analysis += "This product has good potential but consider the competition."
    else:
        analysis += "This product may face challenges in the market."
        
    return analysis

def process_query(query, product_cache=None):
    """Process the user query and return a response"""
    client = get_openai_client()
    
    # Initialize or use existing product cache
    if product_cache is None:
        product_cache = {}
    
    # Very simple intent detection
    if "recommend" in query.lower() or "product" in query.lower() or "suggest" in query.lower():
        # Product recommendation intent
        products = get_product_recommendations(query, num_results=5)
        
        # Update the product cache in session state
        for i, product in enumerate(products, 1):
            product_cache[i] = product
        
        return format_product_recommendations(query, products), product_cache
    elif "analyze" in query.lower() and any(word in query.lower() for word in ["product", "item"]):
        # Check for analyze intent with product number
        product_index = None
        words = query.lower().split()
        for i, word in enumerate(words):
            if word in ["product", "item"] and i < len(words) - 1 and words[i+1].isdigit():
                product_index = int(words[i+1])
                break
            elif word.isdigit() and i > 0 and words[i-1] in ["product", "item"]:
                product_index = int(word)
                break
        
        if product_index and product_index in product_cache:
            product = product_cache[product_index]
            return analyze_product(product), product_cache
        else:
            return "I don't have information about that product. Please search for products first.", product_cache
    else:
        # For all other intents, use OpenAI to generate a response
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an e-commerce assistant helping with general questions."},
                    {"role": "user", "content": query}
                ],
                max_tokens=150
            )
            return response.choices[0].message.content, product_cache
        except Exception as e:
            return "I'm having trouble generating a response right now. Please try asking about product recommendations.", product_cache

# Initialize conversation store
conversation_store = ConversationStore()

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "product_cache" not in st.session_state:
    st.session_state.product_cache = {}

# App title
st.title("E-commerce Agent Team")
st.markdown("Welcome to your AI-powered e-commerce assistant. Ask about products, get recommendations, or get help with shopping decisions.")
    
# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if prompt := st.chat_input("How can I help you with your e-commerce needs?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Get response from lead agent
        response, st.session_state.product_cache = process_query(prompt, st.session_state.product_cache)
        
        # Display the response
        message_placeholder.markdown(response)
        
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
    
    # Save conversation to database
    conversation_store.save_conversation(
        user_input=prompt,
        assistant_response=response,
        timestamp=datetime.now()
    )

# Sidebar with options
with st.sidebar:
    st.title("Agent Settings")
    st.write("Manage your e-commerce agent team")
    
    # Add settings and controls
    st.markdown("### Settings")
    
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        st.session_state.product_cache = {}
        st.rerun() 
    
    # Add some examples to help users get started
    st.markdown("### Example Queries")
    example_queries = [
        "What headphones do you recommend?",
        "I need a water bottle that keeps drinks cold",
        "Do you have any t-shirts?",
        "What are trending beauty products?",
        "Find me bathroom products"
    ]
    
    for query in example_queries:
        if st.button(query):
            # When clicked, this will be used as the input
            st.session_state.messages.append({"role": "user", "content": query})
            with st.chat_message("user"):
                st.markdown(query)
                
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                response, st.session_state.product_cache = process_query(query, st.session_state.product_cache)
                message_placeholder.markdown(response)
                
            st.session_state.messages.append({"role": "assistant", "content": response})
            conversation_store.save_conversation(
                user_input=query,
                assistant_response=response,
                timestamp=datetime.now()
            )
            st.rerun() 