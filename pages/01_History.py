import streamlit as st
from database.conversation_store import ConversationStore
import pandas as pd
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Conversation History",
    page_icon="📊",
    layout="wide"
)

# Initialize database
conversation_store = ConversationStore()

# Page title
st.title("Conversation History")

# Get conversation history
@st.cache_data(ttl=60)  # Cache data for 60 seconds
def load_conversation_history(limit=50):
    conversations = conversation_store.get_conversation_history(limit=limit)
    
    # Convert to DataFrame for easier display
    if conversations:
        df = pd.DataFrame(conversations)
        
        # Convert ISO timestamp strings to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Sort by timestamp (newest first)
        df = df.sort_values('timestamp', ascending=False)
        
        return df
    else:
        return pd.DataFrame(columns=['id', 'user_input', 'assistant_response', 'timestamp'])

# Load conversation history
conversation_df = load_conversation_history()

if conversation_df.empty:
    st.info("No conversation history found. Start chatting with the agent to record conversations.")
else:
    # Add filters
    st.subheader("Filter Conversations")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date range filter
        min_date = conversation_df['timestamp'].min().date()
        max_date = conversation_df['timestamp'].max().date()
        
        date_range = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
    
    with col2:
        # Text search
        search_term = st.text_input("Search in conversations")
    
    # Apply filters
    filtered_df = conversation_df.copy()
    
    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = filtered_df[
            (filtered_df['timestamp'].dt.date >= start_date) & 
            (filtered_df['timestamp'].dt.date <= end_date)
        ]
    
    if search_term:
        filtered_df = filtered_df[
            filtered_df['user_input'].str.contains(search_term, case=False) | 
            filtered_df['assistant_response'].str.contains(search_term, case=False)
        ]
    
    # Display conversations
    st.subheader("Conversations")
    
    if filtered_df.empty:
        st.info("No conversations match your filters.")
    else:
        for _, row in filtered_df.iterrows():
            with st.expander(f"{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} - {row['user_input'][:50]}..."):
                st.markdown("**User:**")
                st.markdown(row['user_input'])
                st.markdown("**Assistant:**")
                st.markdown(row['assistant_response'])
                st.markdown(f"**Conversation ID:** {row['id']}")
                
    # Add export button
    if st.button("Export Conversations (CSV)"):
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"conversation_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        ) 