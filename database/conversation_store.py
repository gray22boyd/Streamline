import sqlite3
import os
import json
import streamlit as st
from datetime import datetime

class ConversationStore:
    """
    Handles storage and retrieval of conversation history and products using SQLite.
    """
    
    def __init__(self, db_path='conversations.db'):
        """
        Initialize the conversation store with a database path
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        # Ensure db_path is accessible in the current environment
        # For Streamlit Cloud, we need to make sure the path is writable
        if os.environ.get('STREAMLIT_CLOUD') or 'STREAMLIT_RUNTIME_ROOT' in os.environ:
            # On Streamlit Cloud, use a path in the mounted filesystem
            try:
                # First try the mount directory
                self.db_path = os.path.join('/mount/src/streamline', db_path)
                
                # If that's not writable, try a temporary directory
                if not os.access(os.path.dirname(self.db_path), os.W_OK):
                    import tempfile
                    temp_dir = tempfile.gettempdir()
                    self.db_path = os.path.join(temp_dir, db_path)
                    st.warning(f"Using temporary directory for database: {self.db_path}")
            except Exception as e:
                # Fall back to default path
                self.db_path = db_path
                st.warning(f"Using default path for database: {self.db_path}")
        else:
            self.db_path = db_path
            
        # Create directory if it doesn't exist
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        self._initialize_db()
        self._migrate_schema_if_needed()  # Check for needed schema migrations
        
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
        
    def _migrate_schema_if_needed(self):
        """
        Check if database schema needs to be migrated and perform necessary updates
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if sales_estimate column exists in the products table
        cursor.execute("PRAGMA table_info(products)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        schema_needs_update = False
        
        # Check if sales_estimate column needs to be removed
        if 'sales_estimate' in column_names:
            schema_needs_update = True
            print("Migrating database schema: Removing sales_estimate column...")
        
        # Check if we need to add ad pressure columns
        if 'ad_pressure_level' not in column_names:
            schema_needs_update = True
            print("Migrating database schema: Adding sponsored ads and ad pressure columns...")
        
        if schema_needs_update:
            # Create new table with updated schema
            cursor.execute('''
                CREATE TABLE products_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asin TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    brand TEXT,
                    price REAL,
                    wholesale_price REAL,
                    rating REAL,
                    review_count INTEGER,
                    best_seller_rank INTEGER,
                    profit_margin REAL,
                    category TEXT,
                    image_url TEXT,
                    amazon_link TEXT,
                    score REAL,
                    is_sponsored BOOLEAN,
                    sponsored_count INTEGER,
                    ad_pressure_level TEXT,
                    ad_pressure_score INTEGER,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            # Create column list based on what exists in old table
            old_columns = []
            for col_name in column_names:
                if col_name != 'sales_estimate':  # Skip the column we're removing
                    old_columns.append(col_name)
            
            # Create placeholders for new columns
            new_column_values = {}
            if 'is_sponsored' not in column_names:
                new_column_values['is_sponsored'] = 0
            if 'sponsored_count' not in column_names:
                new_column_values['sponsored_count'] = 0
            if 'ad_pressure_level' not in column_names:
                new_column_values['ad_pressure_level'] = "'Unknown'"
            if 'ad_pressure_score' not in column_names:
                new_column_values['ad_pressure_score'] = 0
            
            # Build the SQL statement to copy data
            source_columns = ', '.join(old_columns)
            target_columns = source_columns
            values = source_columns
            
            # Add new columns to the target and values
            for col, default_val in new_column_values.items():
                target_columns += f", {col}"
                values += f", {default_val}"
            
            # Copy data from old table to new table
            cursor.execute(f'''
                INSERT INTO products_new 
                ({target_columns})
                SELECT {values}
                FROM products
            ''')
            
            # Drop old table
            cursor.execute('DROP TABLE products')
            
            # Rename new table to original name
            cursor.execute('ALTER TABLE products_new RENAME TO products')
            
            conn.commit()
            print("Database schema migration completed successfully.")
        
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
        profit_margin = product_data.get('profit_margin', 0)
        category = product_data.get('category', '')
        image_url = product_data.get('image_url', '')
        amazon_link = product_data.get('amazon_link', '')
        score = product_data.get('score', 0)
        is_sponsored = product_data.get('is_sponsored', False)
        sponsored_count = product_data.get('sponsored_count', 0)
        ad_pressure_level = product_data.get('ad_pressure_level', 'Unknown')
        ad_pressure_score = product_data.get('ad_pressure_score', 0)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Use INSERT OR REPLACE to update the product if it already exists
        cursor.execute('''
            INSERT OR REPLACE INTO products 
            (asin, title, brand, price, wholesale_price, rating, review_count, 
            best_seller_rank, profit_margin, category, 
            image_url, amazon_link, score, is_sponsored, sponsored_count,
            ad_pressure_level, ad_pressure_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            asin, title, brand, price, wholesale_price, rating, review_count,
            best_seller_rank, profit_margin, category,
            image_url, amazon_link, score, is_sponsored, sponsored_count,
            ad_pressure_level, ad_pressure_score, timestamp_str
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
                             'profit_margin', 'ad_pressure_level', 'timestamp']
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
        
        # Special handling for ad_pressure_level since it's Low/Medium/High
        if sort_by == 'ad_pressure_level':
            # For ad pressure, we want to sort by: High, Medium, Low (or reverse)
            # Use CASE statement to convert text values to numeric for proper sorting
            order_clause = f"""
            ORDER BY CASE ad_pressure_level 
                WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'Low' THEN 3
                ELSE 4
            END {sort_order}
            """
            query += order_clause
        else:
            query += f" ORDER BY {sort_by} {sort_order}"
            
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        products = []
        for row in cursor.fetchall():
            products.append(dict(row))
            
        conn.close()
        
        return products 