import os
import requests
import json
import hmac
import hashlib
import time
import boto3
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ProductAgent:
    """
    Product Agent is responsible for product recommendations and answering 
    product-related questions. Uses Amazon SP API and Rainforest API for data.
    """
    
    def __init__(self):
        """Initialize the product agent with API clients"""
        # OpenAI client for intent analysis
        openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Amazon SP API credentials
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY")
        self.aws_secret_key = os.getenv("AWS_SECRET_KEY")
        self.amazon_client_id = os.getenv("AMAZON_CLIENT_ID")
        self.amazon_client_secret = os.getenv("AMAZON_CLIENT_SECRET")
        self.amazon_access_token = os.getenv("AMAZON_ACCESS_TOKEN")
        
        # Rainforest API credentials
        self.rainforest_api_key = os.getenv("RAINFOREST_API_KEY")
        
        # Initialize the session for Amazon SP API
        self.session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name="us-east-1"  # Default region for Amazon SP API
        )
        
    def get_product_recommendations(self, query, num_results=5, category=None):
        """
        Get product recommendations based on the user query
        Uses Amazon SP API for initial search and Rainforest for additional data
        
        Args:
            query (str): The user query to base recommendations on
            num_results (int): Number of recommendations to return
            category (str, optional): Specific category to search within
            
        Returns:
            list: A list of recommended product dictionaries with enhanced data
        """
        # Step 1: Extract search terms and category from the query
        search_info = self._extract_search_info(query)
        
        if category:
            search_info['category'] = category
            
        # Step 2: Search for products using Amazon SP API
        amazon_products = self._search_amazon_products(
            search_terms=search_info['search_terms'],
            category=search_info['category'],
            limit=num_results
        )
        
        if not amazon_products:
            return []
            
        # Step 3: Enrich products with Rainforest API data
        enriched_products = []
        for product in amazon_products:
            asin = product.get("asin")
            if asin:
                # Get additional data from Rainforest
                enriched_data = self._get_rainforest_product_data(asin)
                if enriched_data:
                    # Combine Amazon and Rainforest data
                    combined_product = {**product, **enriched_data}
                    # Calculate product score
                    combined_product['score'] = self._calculate_product_score(combined_product)
                    enriched_products.append(combined_product)
        
        # Step 4: Sort products by score (descending)
        enriched_products.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return enriched_products[:num_results]
    
    def _extract_search_info(self, query):
        """
        Extract search terms and category from the query using OpenAI
        
        Args:
            query (str): The user's search query
            
        Returns:
            dict: Dictionary with search_terms and category
        """
        prompt = f"""
        Extract the main search terms and product category from this query: "{query}"
        Format your response as JSON with these fields:
        - search_terms: The main search terms to look for products
        - category: The product category (use None if not specified)

        For example:
        Query: "Find me trending bathroom products"
        Response: {{"search_terms": "trending bathroom products", "category": "Bathroom"}}
        
        Query: "What are popular kitchen gadgets under $50"
        Response: {{"search_terms": "popular kitchen gadgets", "category": "Kitchen"}}
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You extract search terms and categories from queries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                'search_terms': result.get('search_terms', query),
                'category': result.get('category')
            }
        except Exception as e:
            print(f"Error extracting search info: {e}")
            return {'search_terms': query, 'category': None}
    
    def _sign_request(self, method, uri, query_string='', payload=''):
        """
        Sign a request with AWS Signature Version 4
        
        Args:
            method (str): HTTP method (GET, POST, etc.)
            uri (str): Request URI
            query_string (str): Query string
            payload (str): Request payload
            
        Returns:
            tuple: (url, headers) The signed URL and headers for the request
        """
        # Step 1: Create request date and unique request credentials
        now = datetime.utcnow()
        amz_date = now.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = now.strftime('%Y%m%d')
        
        # Set up the canonical URI, host, and endpoint
        host = 'sellingpartnerapi-na.amazon.com'
        canonical_uri = uri
        endpoint = f'https://{host}'
        
        # Create canonical headers
        canonical_headers = (
            f'host:{host}\n'
            f'x-amz-date:{amz_date}\n'
        )
        
        # Create signed headers
        signed_headers = 'host;x-amz-date'
        
        # Step 2: Create canonical request
        if method == 'GET' and query_string:
            canonical_request = f"{method}\n{canonical_uri}\n{query_string}\n{canonical_headers}\n{signed_headers}\n{hashlib.sha256(b'').hexdigest()}"
        else:
            canonical_request = f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
        
        # Step 3: Create string to sign
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f"{date_stamp}/us-east-1/execute-api/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        
        # Step 4: Calculate signature
        # Create signing key
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        signing_key = sign(('AWS4' + self.aws_secret_key).encode('utf-8'), date_stamp)
        signing_key = sign(signing_key, 'us-east-1')
        signing_key = sign(signing_key, 'execute-api')
        signing_key = sign(signing_key, 'aws4_request')
        
        # Calculate signature
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # Step 5: Create authorization header
        auth_header = (
            f"{algorithm} "
            f"Credential={self.aws_access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        
        # Create request URL and headers
        if query_string:
            url = f"{endpoint}{canonical_uri}?{query_string}"
        else:
            url = f"{endpoint}{canonical_uri}"
        
        # Create headers
        headers = {
            'x-amz-date': amz_date,
            'Authorization': auth_header,
            'x-amz-access-token': self.amazon_access_token,
            'Content-Type': 'application/json'
        }
        
        return url, headers
    
    def _search_amazon_products(self, search_terms, category=None, limit=5):
        """
        Search for products using Amazon SP API with manual AWS Signature Version 4
        
        Args:
            search_terms (str): Search terms to find products
            category (str, optional): Category to filter by
            limit (int): Maximum number of products to return
            
        Returns:
            list: List of product dictionaries from Amazon
        """
        try:
            print(f"Searching Amazon for: {search_terms} in category: {category}")
            
            # Build the request URI and parameters
            uri = '/catalog/2022-04-01/items'
            
            # Prepare query parameters
            query_params = {
                'keywords': search_terms,
                'marketplaceIds': 'ATVPDKIKX0DER',  # US marketplace
                'includedData': 'summaries,images,attributes,dimensions,identifiers,productTypes,relationships,salesRanks',
                'pageSize': str(limit)
            }
            
            if category:
                query_params['productType'] = category
                
            # Create query string
            query_string = urlencode(query_params)
            
            # Sign the request using AWS Signature Version 4
            url, headers = self._sign_request('GET', uri, query_string)
            
            # Make the request
            response = requests.get(url, headers=headers)
            
            # Process the response
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                # Format the response
                products = []
                for item in items:
                    # Extract product details
                    asin = item.get('asin', '')
                    
                    # Get summary information
                    summary = {}
                    if 'summaries' in item and len(item['summaries']) > 0:
                        summary = item['summaries'][0]
                    
                    title = summary.get('title', '')
                    brand = summary.get('brandName', '')
                    
                    # Get product type/category
                    category = ''
                    if 'productTypes' in item and len(item['productTypes']) > 0:
                        category = item['productTypes'][0].get('name', '')
                    
                    # Get image URL
                    image_url = ''
                    if 'images' in item and len(item['images']) > 0:
                        primary_images = [img for img in item['images'] if img.get('variant') == 'MAIN']
                        if primary_images:
                            image_url = primary_images[0].get('link', '')
                        else:
                            image_url = item['images'][0].get('link', '')
                    
                    # Get price from attributes if available
                    price = 0
                    if 'attributes' in item:
                        for attr in item['attributes']:
                            if attr.get('name') == 'ListPrice':
                                price_str = attr.get('value', '0')
                                try:
                                    price = float(price_str)
                                except ValueError:
                                    price = 0
                                break
                    
                    # Create the product dictionary
                    product = {
                        "asin": asin,
                        "title": title,
                        "brand": brand,
                        "price": price,
                        "category": category,
                        "image_url": image_url
                    }
                    products.append(product)
                
                return products
            else:
                print(f"Error from Amazon SP API: {response.status_code} - {response.text}")
                # Fallback to Rainforest API for search
                return self._search_rainforest_products(search_terms, category, limit)
            
        except Exception as e:
            print(f"Error searching Amazon products: {e}")
            # Fall back to Rainforest API
            return self._search_rainforest_products(search_terms, category, limit)
    
    def _search_rainforest_products(self, search_terms, category=None, limit=5):
        """
        Search for products using Rainforest API as a fallback
        
        Args:
            search_terms (str): Search terms to find products
            category (str, optional): Category to filter by
            limit (int): Maximum number of products to return
            
        Returns:
            list: List of product dictionaries from Rainforest
        """
        try:
            print(f"Falling back to Rainforest API for search: {search_terms}")
            
            # Build the request parameters
            params = {
                'api_key': self.rainforest_api_key,
                'type': 'search',
                'amazon_domain': 'amazon.com',
                'search_term': search_terms,
                'sort_by': 'featured'
            }
            
            if category:
                # Convert category to Amazon department format if possible
                params['search_filter'] = f"department:{category}"
            
            # Make the request
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                search_results = data.get('search_results', [])
                
                products = []
                for item in search_results:
                    product = {
                        "asin": item.get('asin', ''),
                        "title": item.get('title', ''),
                        "brand": item.get('brand', {}).get('name', ''),
                        "price": float(item.get('price', {}).get('value', 0)),
                        "category": item.get('categories', [{}])[0].get('name', '') if item.get('categories') else '',
                        "image_url": item.get('image', '')
                    }
                    products.append(product)
                
                return products[:limit]
            else:
                print(f"Error from Rainforest API: {response.text}")
                return []
                
        except Exception as e:
            print(f"Error searching Rainforest products: {e}")
            return []
    
    def _get_rainforest_product_data(self, asin):
        """
        Get additional product data from Rainforest API
        
        Args:
            asin (str): Amazon ASIN for the product
            
        Returns:
            dict: Additional product data from Rainforest
        """
        try:
            print(f"Getting Rainforest data for ASIN: {asin}")
            
            # Build the request parameters
            params = {
                'api_key': self.rainforest_api_key,
                'type': 'product',
                'amazon_domain': 'amazon.com',
                'asin': asin,
                'include_data': 'ratings,pricing,bestsellers_rank'
            }
            
            # Make the request
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                product = data.get('product', {})
                
                # Extract all the data we need
                rating = product.get('rating', 0)
                review_count = product.get('ratings_total', 0)
                retail_price = float(product.get('buybox_winner', {}).get('price', {}).get('value', 0))
                
                # Get best seller rank
                best_seller_rank = 999
                bestseller_ranks = product.get('bestsellers_rank', [])
                if bestseller_ranks and len(bestseller_ranks) > 0:
                    # Use the first/primary rank
                    best_seller_rank = bestseller_ranks[0].get('rank', 999)
                
                # Estimate wholesale price (typically 50-60% of retail)
                # This is an estimation - in reality, you'd need supplier data
                wholesale_price = round(retail_price * 0.55, 2)
                
                # Calculate profit margin
                if retail_price > 0 and wholesale_price > 0:
                    profit_margin = ((retail_price - wholesale_price) / retail_price) * 100
                else:
                    profit_margin = 0
                
                # Estimate monthly sales based on BSR
                # This is a very rough estimation algorithm
                # In reality, you'd need a more sophisticated model
                if best_seller_rank < 100:
                    sales_estimate = 10000 + (100 - best_seller_rank) * 200
                elif best_seller_rank < 1000:
                    sales_estimate = 3000 + (1000 - best_seller_rank) * 7
                elif best_seller_rank < 10000:
                    sales_estimate = 500 + (10000 - best_seller_rank) * 0.25
                else:
                    sales_estimate = max(100, 500 - (best_seller_rank - 10000) * 0.05)
                
                sales_estimate = int(sales_estimate)
                
                # Get the Amazon URL
                amazon_link = f"https://www.amazon.com/dp/{asin}"
                
                return {
                    "wholesale_price": wholesale_price,
                    "amazon_link": amazon_link,
                    "rating": rating,
                    "review_count": review_count,
                    "best_seller_rank": best_seller_rank,
                    "sales_estimate": sales_estimate,
                    "profit_margin": round(profit_margin, 2)
                }
            else:
                print(f"Error from Rainforest API: {response.text}")
                return {}
            
        except Exception as e:
            print(f"Error getting Rainforest data: {e}")
            return {}
    
    def _calculate_product_score(self, product):
        """
        Calculate a weighted score for a product based on multiple factors
        
        Args:
            product (dict): Product data with both Amazon and Rainforest info
            
        Returns:
            float: Weighted score for the product
        """
        # Define weights for different factors
        weights = {
            'rating': 0.25,          # Product rating (0-5)
            'review_count': 0.15,    # Number of reviews
            'rank': 0.20,            # Best seller rank (inverse)
            'profit_margin': 0.30,   # Profit margin
            'sales': 0.10            # Sales estimate
        }
        
        # Get values (with defaults if missing)
        rating = product.get('rating', 0) 
        review_count = min(product.get('review_count', 0) / 5000, 1)  # Normalize to 0-1
        best_seller_rank = product.get('best_seller_rank', 1000)
        rank_score = 1 - min(best_seller_rank / 100, 1)  # Normalize and invert
        profit_margin = min(product.get('profit_margin', 0) / 100, 1)  # Normalize to 0-1
        sales = min(product.get('sales_estimate', 0) / 20000, 1)  # Normalize to 0-1
        
        # Calculate weighted score
        score = (
            weights['rating'] * (rating / 5) +
            weights['review_count'] * review_count +
            weights['rank'] * rank_score +
            weights['profit_margin'] * profit_margin +
            weights['sales'] * sales
        )
        
        return round(score * 100, 2)  # Return as 0-100 score
    
    def get_product_details(self, asin):
        """
        Get detailed information about a specific product by ASIN
        
        Args:
            asin (str): The Amazon ASIN of the product
            
        Returns:
            dict: The complete product details or None if not found
        """
        try:
            # Try to get product data directly from Rainforest
            # (More reliable for detailed product info)
            params = {
                'api_key': self.rainforest_api_key,
                'type': 'product',
                'amazon_domain': 'amazon.com',
                'asin': asin
            }
            
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                rf_product = data.get('product', {})
                
                # Extract basic product data
                product = {
                    "asin": asin,
                    "title": rf_product.get('title', ''),
                    "brand": rf_product.get('brand', ''),
                    "price": float(rf_product.get('buybox_winner', {}).get('price', {}).get('value', 0)),
                    "category": rf_product.get('categories', [{}])[0].get('name', '') if rf_product.get('categories') else '',
                    "image_url": rf_product.get('main_image', {}).get('link', '')
                }
                
                # Get additional data from Rainforest
                enriched_data = self._get_rainforest_product_data(asin)
                
                # Combine data
                if enriched_data:
                    product.update(enriched_data)
                    product['score'] = self._calculate_product_score(product)
                    
                return product
            else:
                print(f"Error getting product details from Rainforest: {response.text}")
                return None
                
        except Exception as e:
            print(f"Error getting product details: {e}")
            return None
            
    def analyze_product(self, product):
        """
        Provide a detailed analysis of a product with passion product ideas
        
        Args:
            product (dict): The product data to analyze
            
        Returns:
            str: Detailed analysis with passion product ideas
        """
        if not product:
            return "No product data available for analysis."
            
        # Extract basic product information
        title = product.get('title', 'Unknown Product')
        brand = product.get('brand', 'Unknown Brand')
        category = product.get('category', 'Uncategorized')
        asin = product.get('asin', '')
        retail_price = product.get('price', 0)
        wholesale_price = product.get('wholesale_price', 0)
        profit_margin = product.get('profit_margin', 0)
        rating = product.get('rating', 0)
        review_count = product.get('review_count', 0)
        best_seller_rank = product.get('best_seller_rank', 'N/A')
        sales_estimate = product.get('sales_estimate', 0)
        score = product.get('score', 0)
        
        # Build the analysis
        analysis = f"# Product Analysis: {title}\n\n"
        
        # Basic information
        analysis += "## Product Overview\n"
        analysis += f"- **Title:** {title}\n"
        analysis += f"- **Brand:** {brand}\n"
        analysis += f"- **Category:** {category}\n"
        analysis += f"- **ASIN:** {asin}\n"
        analysis += f"- **Overall Score:** {score}/100\n\n"
        
        # Financial analysis
        analysis += "## Financial Analysis\n"
        analysis += f"- **Retail Price:** ${retail_price:.2f}\n"
        analysis += f"- **Wholesale Price:** ${wholesale_price:.2f}\n"
        analysis += f"- **Profit Margin:** {profit_margin:.2f}%\n"
        
        # Calculate profit per unit
        profit_per_unit = retail_price - wholesale_price
        analysis += f"- **Profit Per Unit:** ${profit_per_unit:.2f}\n"
        
        # Calculate monthly profit potential
        monthly_profit = profit_per_unit * sales_estimate
        analysis += f"- **Estimated Monthly Profit:** ${monthly_profit:.2f}\n\n"
        
        # Market analysis
        analysis += "## Market Performance\n"
        analysis += f"- **Rating:** {rating}/5 ({review_count} reviews)\n"
        analysis += f"- **Best Seller Rank:** {best_seller_rank}\n"
        analysis += f"- **Estimated Monthly Sales:** {sales_estimate} units\n\n"
        
        # Determine viability level
        viability = "Low"
        if score >= 70:
            viability = "High"
        elif score >= 40:
            viability = "Medium"
            
        analysis += f"## Overall E-commerce Viability: {viability}\n\n"
        
        # Generate competition and risk assessment
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
            
        analysis += f"- **Competition Level:** {competition}\n"
        analysis += f"- **Risk Level:** {risk}\n\n"
        
        # Generate passion product ideas
        passion_ideas = self._generate_passion_product_ideas(title, category)
        if passion_ideas:
            analysis += "## Passion Product Ideas\n"
            analysis += passion_ideas + "\n\n"
        
        # Final recommendation
        analysis += "## Recommendation\n"
        if score >= 70:
            analysis += "- **Strong potential** for direct selling or creating passion products\n"
            analysis += "- Consider starting with small inventory test orders\n"
            analysis += "- High profit margin and proven sales history make this a promising opportunity\n"
        elif score >= 40:
            analysis += "- **Moderate potential** requires careful consideration\n"
            analysis += "- Explore ways to differentiate or add value through passion products\n"
            analysis += "- Test market with minimal investment before scaling\n"
        else:
            analysis += "- **Limited direct selling potential**\n"
            analysis += "- Consider only if you have unique improvements or market positioning\n"
            analysis += "- High risk relative to potential reward\n"
        
        return analysis
    
    def _generate_passion_product_ideas(self, title, category):
        """
        Generate passion product ideas using OpenAI
        
        Args:
            title (str): Product title
            category (str): Product category
            
        Returns:
            str: Passion product ideas or empty string if generation fails
        """
        try:
            prompt = f"""
            Suggest 3 creative ways to improve or build upon this product for a new ecommerce business. 
            Think in terms of Passion Products: solving complaints, enhancing features, or creating niche-focused upgrades.
            
            Product: {title}
            Category: {category}
            
            Keep your answer under 100 words total.
            Format as a numbered list with short, clear suggestions.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You generate creative e-commerce product improvement ideas."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            ideas = response.choices[0].message.content.strip()
            return ideas
            
        except Exception as e:
            print(f"Error generating passion product ideas: {e}")
            return "" 