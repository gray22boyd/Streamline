import streamlit as st
import os
import json
import sys
from datetime import datetime
import traceback

# Add the current directory to the path to ensure modules can be found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Try importing the required modules with error handling
try:
    from agents.lead_agent import LeadAgent
    from database.conversation_store import ConversationStore
except ImportError as e:
    # Try alternative import approach
    try:
        st.write("Attempting alternative import approach...")
        import agents.lead_agent
        import database.conversation_store
        LeadAgent = agents.lead_agent.LeadAgent
        ConversationStore = database.conversation_store.ConversationStore
    except ImportError as e2:
        st.error(f"""
        **Error: Failed to import required modules.**
        
        This could be due to incorrect Python package structure or missing dependencies.
        
        Technical details:
        {str(e2)}
        
        If you're deploying to Streamlit Cloud, check that:
        1. All required packages are in requirements.txt
        2. Your project structure is correct
        3. Environment variables are set in Streamlit Cloud
        """)
        # Show traceback but clean it to avoid exposing sensitive info
        st.code(traceback.format_exc(), language="python")
        st.stop()

# Page configuration
st.set_page_config(
    page_title="E-commerce Agent Team",
    page_icon="🤖",
    layout="wide"
)

# Initialize database
try:
    conversation_store = ConversationStore()
except Exception as e:
    st.error(f"""
    **Error initializing database.**
    
    {str(e)}
    """)
    st.code(traceback.format_exc(), language="python")
    st.stop()

# Initialize agents
@st.cache_resource
def initialize_lead_agent():
    try:
        return LeadAgent()
    except Exception as e:
        st.error(f"Failed to initialize LeadAgent: {str(e)}")
        return None

lead_agent = initialize_lead_agent()
if lead_agent is None:
    st.error("Cannot continue without the Lead Agent. Please check logs for errors.")
    st.stop()

# App title
st.title("E-commerce Agent Team")
st.markdown("Welcome to your AI-powered e-commerce assistant. Ask about products, get recommendations, or get help with shopping decisions.")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
    
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
        response = lead_agent.process_query(prompt)
        
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
    
    # Add links to other pages
    st.markdown("### Navigation")
    st.markdown("- [Home](.) (current page)")
    st.markdown("- [Conversation History](/History)")
    st.markdown("- [Products Database](/Products)")
    
    # Add settings and controls
    st.markdown("### Settings")
    
    if st.button("Clear Conversation"):
        st.session_state.messages = []
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
                response = lead_agent.process_query(query)
                message_placeholder.markdown(response)
                
            st.session_state.messages.append({"role": "assistant", "content": response})
            conversation_store.save_conversation(
                user_input=query,
                assistant_response=response,
                timestamp=datetime.now()
            )
            st.rerun() 