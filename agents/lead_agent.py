import os
from openai import OpenAI
from dotenv import load_dotenv
from agents.product_agent import ProductAgent
from database.conversation_store import ConversationStore

# Load environment variables
load_dotenv()

class LeadAgent:
    """
    Lead Agent is responsible for managing user queries and delegating tasks to specialized agents if needed.
    This is the main entry point for all user interactions.
    """
    
    def __init__(self):
        """Initialize the lead agent with the OpenAI client and specialized agents"""
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        
        # Initialize specialized agents
        self.product_agent = ProductAgent()
        
        # Initialize database
        self.conversation_store = ConversationStore()
        
        # Cache for products to enable analysis of previously seen products
        self.product_cache = {}
        
    def process_query(self, query):
        """
        Process the user query and return a response
        
        Args:
            query (str): The user's query text
            
        Returns:
            str: The agent's response
        """
        print(f"Processing query: {query}")
        
        # Check for product analysis request first
        analysis_intent, product_index = self._check_for_analysis_intent(query)
        if analysis_intent and product_index is not None:
            if product_index in self.product_cache:
                return self._analyze_product_for_ecommerce(self.product_cache[product_index])
            else:
                return "I don't have information about that product. Please search for products first."
        
        # Determine query intent
        intent = self._determine_query_intent(query)
        
        # Route to appropriate specialized agent based on intent
        if intent == "product_recommendation":
            products = self.product_agent.get_product_recommendations(query, num_results=5)
            # Cache products for later analysis
            self.product_cache = {i+1: product for i, product in enumerate(products)}
            
            # Save products to the database
            for product in products:
                self.conversation_store.save_product(product)
                
            return self._format_product_recommendations(query, products)
        elif intent == "product_info":
            # Extract product identifier if present
            asin = self._extract_asin(query)
            if asin:
                product = self.product_agent.get_product_details(asin)
                if product:
                    # Save the product to the database
                    self.conversation_store.save_product(product)
                    
                    if "analyze" in query.lower():
                        return self._analyze_product_for_ecommerce(product)
                    else:
                        return self._format_product_info(product)
            
            # If no specific ASIN or product not found, get a recommendation
            products = self.product_agent.get_product_recommendations(query, num_results=1)
            if products:
                # Save products to the database
                for product in products:
                    self.conversation_store.save_product(product)
                    
                return self._format_product_info(products[0])
            else:
                return "I couldn't find information about that product. Could you provide more details?"
        else:
            # For all other intents, use OpenAI to generate a response
            return self._get_response_from_openai(query)
    
    def _check_for_analysis_intent(self, query):
        """
        Check if the query is asking to analyze a specific product
        
        Args:
            query (str): The user's query
            
        Returns:
            tuple: (bool, int or None) Whether this is an analysis request and which product index
        """
        query_lower = query.lower()
        # Check for analysis keywords
        analysis_keywords = ["analyze product", "analyze item", "evaluate product", "assess product"]
        is_analysis = any(keyword in query_lower for keyword in analysis_keywords)
        
        # Extract product number if present
        product_index = None
        if is_analysis:
            # Try to find a number in the query (product 1, product 2, etc.)
            words = query_lower.split()
            for i, word in enumerate(words):
                if word in ["product", "item"] and i < len(words) - 1 and words[i+1].isdigit():
                    product_index = int(words[i+1])
                    break
                elif word.isdigit() and i > 0 and words[i-1] in ["product", "item"]:
                    product_index = int(word)
                    break
                # Handle "#1", "#2" format
                elif word.startswith("#") and word[1:].isdigit():
                    product_index = int(word[1:])
                    break
                # Handle numbers written as words
                elif word in ["one", "two", "three", "four", "five"]:
                    number_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
                    product_index = number_map[word]
                    break
        
        return is_analysis, product_index
    
    def _extract_asin(self, query):
        """
        Extract an Amazon ASIN from a query if present
        
        Args:
            query (str): The user's query
            
        Returns:
            str or None: The extracted ASIN or None
        """
        # Check for patterns like "B08CRLVK9F" or "information about B08CRLVK9F"
        words = query.split()
        for word in words:
            # ASINs are typically 10 characters with letters and numbers
            if len(word) == 10 and any(c.isalpha() for c in word) and any(c.isdigit() for c in word):
                return word
        return None
        
    def _determine_query_intent(self, query):
        """
        Determine the intent of the user query
        
        Args:
            query (str): The user's query text
            
        Returns:
            str: The intent category
        """
        prompt = f"""
        Categorize the following user query into exactly one of these categories:
        - product_recommendation: User is looking for product suggestions or trending items
        - product_info: User is asking about details of a specific product
        - general_ecommerce: General e-commerce questions about shipping, returns, etc.
        - other: Any other queries
        
        User query: "{query}"
        
        Just return the category name, nothing else.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You categorize user queries into predefined categories."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50
            )
            return response.choices[0].message.content.strip().lower()
        except Exception as e:
            print(f"Error determining query intent: {e}")
            return "other"
        
    def _format_product_recommendations(self, query, products):
        """Format product recommendations into a readable response with enhanced data"""
        if not products:
            return "I couldn't find any products matching your query. Could you try a different search?"
        
        response = f"Based on your search for '{query}', here are the top trending products:\n\n"
        
        for i, product in enumerate(products, 1):
            # Get product details
            title = product.get('title', 'Unknown Product')
            brand = product.get('brand', 'Unknown Brand')
            retail_price = product.get('price', 0)
            wholesale_price = product.get('wholesale_price', 0)
            rating = product.get('rating', 0)
            review_count = product.get('review_count', 0)
            profit_margin = product.get('profit_margin', 0)
            amazon_link = product.get('amazon_link', '')
            score = product.get('score', 0)
            
            # Format the product information with proper vertical spacing
            response += f"**Product #{i} - Score: {score}/100**\n"
            response += f"- **Title:** {title}\n"
            response += f"- **Brand:** {brand}\n"
            response += f"- **Retail Price:** ${retail_price:.2f}\n"
            response += f"- **Wholesale Price:** ${wholesale_price:.2f}\n"
            response += f"- **Profit Margin:** {profit_margin:.2f}%\n"
            response += f"- **Rating:** {rating}/5 ({review_count} reviews)\n"
            if amazon_link:
                response += f"- [View on Amazon]({amazon_link})\n"
            response += "\n"
            
        response += "Would you like more detailed information about any of these products? Reply with 'analyze product #1' (or any number) for a detailed e-commerce analysis."
        return response
    
    def _format_product_info(self, product):
        """Format detailed product information into a readable response"""
        # Get product details
        title = product.get('title', 'Unknown Product')
        brand = product.get('brand', 'Unknown Brand')
        retail_price = product.get('price', 0)
        wholesale_price = product.get('wholesale_price', 0)
        rating = product.get('rating', 0)
        review_count = product.get('review_count', 0)
        category = product.get('category', 'Uncategorized')
        amazon_link = product.get('amazon_link', '')
        best_seller_rank = product.get('best_seller_rank', 'N/A')
        sales_estimate = product.get('sales_estimate', 'N/A')
        profit_margin = product.get('profit_margin', 0)
        score = product.get('score', 0)
        
        response = f"# {title}\n\n"
        response += f"- **Brand:** {brand}\n"
        response += f"- **Category:** {category}\n"
        response += f"- **Overall Score:** {score}/100\n\n"
        
        response += "## Pricing Information\n"
        response += f"- **Retail Price:** ${retail_price:.2f}\n"
        response += f"- **Wholesale Price:** ${wholesale_price:.2f}\n"
        response += f"- **Profit Margin:** {profit_margin:.2f}%\n\n"
        
        response += "## Market Performance\n"
        response += f"- **Rating:** {rating}/5 ({review_count} reviews)\n"
        response += f"- **Best Seller Rank:** {best_seller_rank}\n"
        response += f"- **Estimated Monthly Sales:** {sales_estimate} units\n\n"
        
        if amazon_link:
            response += f"[View on Amazon]({amazon_link})\n\n"
        
        response += "Would you like me to analyze this product for e-commerce viability? Reply with 'analyze this product'."
        return response
    
    def _analyze_product_for_ecommerce(self, product):
        """
        Analyze a product for e-commerce viability
        
        Args:
            product (dict): The product data to analyze
            
        Returns:
            str: Detailed analysis of the product for e-commerce
        """
        # Extract product information
        title = product.get('title', 'Unknown Product')
        brand = product.get('brand', 'Unknown Brand')
        retail_price = product.get('price', 0)
        wholesale_price = product.get('wholesale_price', 0)
        rating = product.get('rating', 0)
        review_count = product.get('review_count', 0)
        category = product.get('category', 'Uncategorized')
        best_seller_rank = product.get('best_seller_rank', 999)
        sales_estimate = product.get('sales_estimate', 0)
        profit_margin = product.get('profit_margin', 0)
        score = product.get('score', 0)
        
        response = f"# E-commerce Analysis: {title}\n\n"
        
        response += "## Product Information\n"
        response += f"- **Title:** {title}\n"
        response += f"- **Brand:** {brand}\n"
        response += f"- **Category:** {category}\n"
        response += f"- **Overall Score:** {score}/100\n\n"
        
        response += "## Financial Analysis\n"
        response += f"- **Retail Price:** ${retail_price:.2f}\n"
        response += f"- **Wholesale Price:** ${wholesale_price:.2f}\n"
        response += f"- **Profit Margin:** {profit_margin:.2f}%\n"
        
        # Calculate profit per unit
        profit_per_unit = retail_price - wholesale_price
        response += f"- **Profit Per Unit:** ${profit_per_unit:.2f}\n"
        
        # Calculate monthly profit potential
        monthly_profit = profit_per_unit * sales_estimate
        response += f"- **Estimated Monthly Profit:** ${monthly_profit:.2f}\n\n"
        
        response += "## Market Analysis\n"
        response += f"- **Rating:** {rating}/5 ({review_count} reviews)\n"
        response += f"- **Best Seller Rank:** {best_seller_rank}\n"
        response += f"- **Estimated Monthly Sales:** {sales_estimate} units\n\n"
        
        # Determine viability level
        viability = "Low"
        if score >= 70:
            viability = "High"
        elif score >= 40:
            viability = "Medium"
            
        response += f"## Overall Viability: {viability}\n\n"
        
        # Generate specific analysis based on the product data
        if review_count == 0:
            competition = "Unknown (No reviews)"
            risk = "High - No proven track record"
        elif review_count < 100:
            competition = "Low to Medium"
            risk = "Medium - Limited market validation"
        elif review_count < 1000:
            competition = "Medium"
            risk = "Medium - Established product with competition"
        else:
            competition = "High"
            risk = "Low - Well-established market"
            
        response += f"- **Competition Level:** {competition}\n"
        response += f"- **Risk Level:** {risk}\n\n"
        
        # Recommendations
        response += "## Recommendations\n"
        
        if score >= 70:
            response += "- **Verdict:** Strong opportunity for e-commerce\n"
            response += "- **Action:** Consider immediate investment\n"
            response += "- High profit margin and proven sales history\n"
            response += "- Consider bundling options to increase average order value\n"
        elif score >= 40:
            response += "- **Verdict:** Moderate opportunity\n"
            response += "- **Action:** Consider testing with small inventory\n"
            response += "- Monitor performance closely before scaling\n"
            response += "- Look for ways to reduce acquisition costs\n"
        else:
            response += "- **Verdict:** Limited opportunity\n"
            response += "- **Action:** Consider alternative products\n"
            response += "- Low profit margin or limited market potential\n"
            response += "- High risk relative to potential reward\n"
            
        return response
        
    def _get_response_from_openai(self, query):
        """Get a response from OpenAI"""
        system_prompt = """
        You are an e-commerce assistant that helps users with their shopping needs.
        You can help with product recommendations, answer questions about products,
        provide information about shipping, returns, and other e-commerce related inquiries.
        Be helpful, concise, and friendly.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"I'm sorry, I encountered an error: {str(e)}. Please try again later." 