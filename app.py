import streamlit as st
import os
import json
from datetime import datetime
from agents.lead_agent import LeadAgent
from database.conversation_store import ConversationStore

# Page configuration
st.set_page_config(
    page_title="E-commerce Agent Team",
    page_icon="🤖",
    layout="wide"
)

# Initialize database
conversation_store = ConversationStore()

# Initialize agents
@st.cache_resource
def initialize_lead_agent():
    return LeadAgent()

lead_agent = initialize_lead_agent()

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
        "What's your return policy?",
        "Tell me about your fitness watches"
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