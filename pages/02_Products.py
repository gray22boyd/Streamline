import streamlit as st
import pandas as pd
from datetime import datetime
from database.conversation_store import ConversationStore

# Page configuration
st.set_page_config(
    page_title="Product Database",
    page_icon="🛍️",
    layout="wide"
)

# Initialize database
conversation_store = ConversationStore()

# Page title
st.title("Product Database")
st.markdown("View and export all products found during your conversations")

# Get product data
@st.cache_data(ttl=60)  # Cache data for 60 seconds
def load_products(category=None, sort_by='score', sort_order='DESC'):
    products = conversation_store.get_products(
        limit=500,  # Get up to 500 products
        category=category,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Convert to DataFrame for easier display
    if products:
        df = pd.DataFrame(products)
        
        # Convert ISO timestamp strings to datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    else:
        return pd.DataFrame(columns=[
            'asin', 'title', 'brand', 'price', 'wholesale_price', 
            'rating', 'review_count', 'best_seller_rank', 'sales_estimate', 
            'profit_margin', 'category', 'score', 'timestamp'
        ])

# Filters and sorting options
st.subheader("Filter and Sort Products")

col1, col2, col3 = st.columns(3)

with col1:
    # Category filter
    categories = ['All Categories']
    all_products = load_products()
    
    if not all_products.empty and 'category' in all_products.columns:
        found_categories = all_products['category'].dropna().unique().tolist()
        categories.extend(sorted(found_categories))
    
    selected_category = st.selectbox("Category", categories)
    category_filter = None if selected_category == 'All Categories' else selected_category

with col2:
    # Sort by field
    sort_options = {
        'score': 'Overall Score',
        'price': 'Retail Price',
        'wholesale_price': 'Wholesale Price',
        'profit_margin': 'Profit Margin',
        'rating': 'Customer Rating',
        'review_count': 'Number of Reviews',
        'best_seller_rank': 'Best Seller Rank',
        'sales_estimate': 'Estimated Sales',
        'timestamp': 'Date Added'
    }
    selected_sort = st.selectbox("Sort by", list(sort_options.values()))
    # Convert display name back to field name
    sort_field = list(sort_options.keys())[list(sort_options.values()).index(selected_sort)]

with col3:
    # Sort order
    sort_direction = st.radio("Sort direction", ['Descending', 'Ascending'], horizontal=True)
    sort_order = 'DESC' if sort_direction == 'Descending' else 'ASC'

# Load products with filters
filtered_products = load_products(
    category=category_filter,
    sort_by=sort_field,
    sort_order=sort_order
)

# Display product count
if not filtered_products.empty:
    st.write(f"Showing {len(filtered_products)} products")
    
    # Add export button
    if st.button("Export Products (CSV)"):
        # Prepare export data
        export_df = filtered_products.copy()
        
        # Format timestamp for CSV
        if 'timestamp' in export_df.columns:
            export_df['timestamp'] = export_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Remove image_url and amazon_link for CSV export
        if 'image_url' in export_df.columns:
            export_df.drop('image_url', axis=1, inplace=True)
        
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Display products in a nice table
    st.subheader("Products")
    
    # Display table with selected columns
    display_columns = [
        'title', 'brand', 'category', 'price', 'wholesale_price', 
        'profit_margin', 'rating', 'review_count', 'sales_estimate', 'score'
    ]
    
    # Keep only columns that exist in the DataFrame
    display_columns = [col for col in display_columns if col in filtered_products.columns]
    
    # Format columns for display
    table_df = filtered_products[display_columns].copy()
    
    # Format currency columns
    for col in ['price', 'wholesale_price']:
        if col in table_df.columns:
            table_df[col] = table_df[col].apply(lambda x: f"${x:.2f}" if pd.notnull(x) else "-")
    
    # Format percentage columns
    if 'profit_margin' in table_df.columns:
        table_df['profit_margin'] = table_df['profit_margin'].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "-")
    
    # Format rating
    if 'rating' in table_df.columns:
        table_df['rating'] = table_df['rating'].apply(lambda x: f"{x}/5" if pd.notnull(x) else "-")
    
    # Format score
    if 'score' in table_df.columns:
        table_df['score'] = table_df['score'].apply(lambda x: f"{x}/100" if pd.notnull(x) else "-")
    
    # Rename columns for display
    rename_map = {
        'title': 'Product Name',
        'brand': 'Brand',
        'category': 'Category',
        'price': 'Retail Price',
        'wholesale_price': 'Wholesale Price',
        'profit_margin': 'Profit Margin',
        'rating': 'Rating',
        'review_count': 'Reviews',
        'sales_estimate': 'Est. Monthly Sales',
        'score': 'Overall Score'
    }
    table_df.rename(columns={k: v for k, v in rename_map.items() if k in table_df.columns}, inplace=True)
    
    # Display the table
    st.dataframe(table_df, use_container_width=True)
    
    # Product details section
    st.subheader("Product Details")
    st.markdown("Select a product from the table above to view detailed information")
    
    # Get list of product titles for selection
    product_titles = filtered_products['title'].tolist()
    selected_title = st.selectbox("Select a product", [''] + product_titles)
    
    if selected_title:
        # Get the selected product
        product = filtered_products[filtered_products['title'] == selected_title].iloc[0].to_dict()
        
        # Display product details in a card
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Show image if available
            if 'image_url' in product and product['image_url']:
                st.image(product['image_url'], width=200)
            else:
                st.markdown("🖼️ *No image available*")
                
            # Amazon link
            if 'amazon_link' in product and product['amazon_link']:
                st.markdown(f"[View on Amazon]({product['amazon_link']})")
        
        with col2:
            # Product details
            st.markdown(f"## {product['title']}")
            st.markdown(f"**Brand:** {product.get('brand', 'Unknown')}")
            st.markdown(f"**Category:** {product.get('category', 'Uncategorized')}")
            st.markdown(f"**Overall Score:** {product.get('score', 0)}/100")
            
            # Financial details
            st.markdown("### Pricing Information")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Retail Price", f"${product.get('price', 0):.2f}")
            
            with col2:
                st.metric("Wholesale Price", f"${product.get('wholesale_price', 0):.2f}")
            
            with col3:
                st.metric("Profit Margin", f"{product.get('profit_margin', 0):.1f}%")
            
            # Market details
            st.markdown("### Market Performance")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Rating", f"{product.get('rating', 0)}/5")
            
            with col2:
                st.metric("Reviews", f"{product.get('review_count', 0)}")
            
            with col3:
                st.metric("Est. Monthly Sales", f"{product.get('sales_estimate', 0)}")
            
            if 'best_seller_rank' in product:
                st.markdown(f"**Best Seller Rank:** {product['best_seller_rank']}")
else:
    st.info("No products found. Start chatting with the agent and ask for product recommendations to populate the database.") 