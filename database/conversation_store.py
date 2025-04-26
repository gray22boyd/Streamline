import sqlite3
import os
import json
from datetime import datetime

class ConversationStore:
    """
    Handles storage and retrieval of conversation history using SQLite.
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