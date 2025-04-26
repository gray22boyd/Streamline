import sqlite3
import os
import json
from datetime import datetime

class ConversationStore:
    """
    Handles storage and retrieval of conversation history and products using SQLite.
    """
    
    def __init__(self, db_path='conversations.db'):
        """
        Initialize the conversation store
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.db_path = db_path
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
            timestamp TEXT NOT NULL,
            metadata TEXT
        )
        ''')
        
        # Create products table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            brand TEXT,
            price REAL,
            wholesale_price REAL,
            rating REAL,
            review_count INTEGER,
            best_seller_rank INTEGER,
            sales_estimate INTEGER,
            profit_margin REAL,
            category TEXT,
            image_url TEXT,
            amazon_link TEXT,
            score REAL,
            timestamp TEXT NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
        
    def save_conversation(self, user_input, assistant_response, timestamp=None, metadata=None):
        """
        Save a conversation exchange to the database
        
        Args:
            user_input (str): The user's input text
            assistant_response (str): The assistant's response text
            timestamp (datetime, optional): The time of the conversation
            metadata (dict, optional): Additional metadata about the conversation
        
        Returns:
            int: The ID of the saved conversation
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        # Convert timestamp to ISO format string
        timestamp_str = timestamp.isoformat()
        
        # Convert metadata to JSON if provided
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata)
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO conversations (user_input, assistant_response, timestamp, metadata) VALUES (?, ?, ?, ?)",
            (user_input, assistant_response, timestamp_str, metadata_json)
        )
        
        # Get the ID of the inserted record
        conversation_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return conversation_id
        
    def get_conversation_history(self, limit=10, offset=0):
        """
        Retrieve recent conversation history
        
        Args:
            limit (int): The maximum number of conversations to retrieve
            offset (int): The offset to start retrieving conversations from
            
        Returns:
            list: A list of conversation dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM conversations ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        
        conversations = []
        for row in cursor.fetchall():
            conversation = dict(row)
            
            # Parse metadata JSON if it exists
            if conversation['metadata']:
                conversation['metadata'] = json.loads(conversation['metadata'])
                
            conversations.append(conversation)
            
        conn.close()
        
        return conversations
    
    def save_product(self, product_data, timestamp=None):
        """
        Save a product to the database, update if it already exists
        
        Args:
            product_data (dict): Product data to save
            timestamp (datetime, optional): The time the product was found
            
        Returns:
            int: The ID of the saved product
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Convert timestamp to ISO format string
        timestamp_str = timestamp.isoformat()
        
        # Extract product fields with default values
        asin = product_data.get('asin', '')
        if not asin:  # Skip products without ASIN
            return None
            
        title = product_data.get('title', 'Unknown Product')
        brand = product_data.get('brand', '')
        price = product_data.get('price', 0)
        wholesale_price = product_data.get('wholesale_price', 0)
        rating = product_data.get('rating', 0)
        review_count = product_data.get('review_count', 0)
        best_seller_rank = product_data.get('best_seller_rank', 0)
        sales_estimate = product_data.get('sales_estimate', 0)
        profit_margin = product_data.get('profit_margin', 0)
        category = product_data.get('category', '')
        image_url = product_data.get('image_url', '')
        amazon_link = product_data.get('amazon_link', '')
        score = product_data.get('score', 0)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Use INSERT OR REPLACE to update the product if it already exists
        cursor.execute('''
            INSERT OR REPLACE INTO products 
            (asin, title, brand, price, wholesale_price, rating, review_count, 
            best_seller_rank, sales_estimate, profit_margin, category, 
            image_url, amazon_link, score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            asin, title, brand, price, wholesale_price, rating, review_count,
            best_seller_rank, sales_estimate, profit_margin, category,
            image_url, amazon_link, score, timestamp_str
        ))
        
        # Get the ID of the inserted or updated record
        product_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return product_id
    
    def get_products(self, limit=100, offset=0, category=None, sort_by='score', sort_order='DESC'):
        """
        Retrieve products from the database
        
        Args:
            limit (int): The maximum number of products to retrieve
            offset (int): The offset to start retrieving products from
            category (str, optional): Filter products by category
            sort_by (str): Field to sort by (score, price, rating, etc.)
            sort_order (str): Sort order ('ASC' or 'DESC')
            
        Returns:
            list: A list of product dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        # Validate sort parameters to prevent SQL injection
        valid_sort_fields = ['score', 'price', 'rating', 'review_count', 'best_seller_rank', 
                             'sales_estimate', 'profit_margin', 'timestamp']
        if sort_by not in valid_sort_fields:
            sort_by = 'score'  # Default to score if invalid
            
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'  # Default to descending if invalid
        
        # Build query based on whether category filter is applied
        query = "SELECT * FROM products"
        params = []
        
        if category:
            query += " WHERE category LIKE ?"
            params.append(f"%{category}%")
            
        query += f" ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        products = []
        for row in cursor.fetchall():
            products.append(dict(row))
            
        conn.close()
        
        return products 