import os
import requests
import json
import hmac
import hashlib
import time
import boto3
import streamlit as st
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
        openai_api_key = st.secrets["openai"]["api_key"] if "openai" in st.secrets else os.getenv("OPENAI_API_KEY")
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Amazon SP API credentials
        self.aws_access_key = st.secrets["aws"]["access_key"] if "aws" in st.secrets else os.getenv("AWS_ACCESS_KEY")
        self.aws_secret_key = st.secrets["aws"]["secret_key"] if "aws" in st.secrets else os.getenv("AWS_SECRET_KEY")
        self.amazon_client_id = st.secrets["amazon"]["client_id"] if "amazon" in st.secrets else os.getenv("AMAZON_CLIENT_ID")
        self.amazon_client_secret = st.secrets["amazon"]["client_secret"] if "amazon" in st.secrets else os.getenv("AMAZON_CLIENT_SECRET")
        self.amazon_access_token = st.secrets["amazon"]["access_token"] if "amazon" in st.secrets else os.getenv("AMAZON_ACCESS_TOKEN")
        
        # Rainforest API credentials
        self.rainforest_api_key = st.secrets["rainforest"]["api_key"] if "rainforest" in st.secrets else os.getenv("RAINFOREST_API_KEY")
        
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
        
        # Step 1.5: Parse filters from the query
        filters = self.parse_query_filters(query)
        
        # If category is provided explicitly, it overrides the one in search_info
        if category:
            search_info['category'] = category
        # If category was found in filters but not in search_info, use it
        elif filters['category'] and not search_info['category']:
            search_info['category'] = filters['category']
        
        # Step 2: Search for products using Amazon SP API
        amazon_products = self._search_amazon_products(
            search_terms=search_info['search_terms'],
            category=search_info['category'],
            limit=max(num_results * 3, 15)  # Request more products to allow for filtering
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
        
        # Step 4: Apply filters from user query
        filtered_products = self._apply_filters(enriched_products, filters)
        
        # Step 5: Sort filtered products by score (descending)
        filtered_products.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return filtered_products[:num_results]
    
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
        Search for products using Rainforest API
        
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
                'include_html': 'false',
                'output': 'json'
            }
            
            if category:
                params['category_id'] = category
                
            # Make the request
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                search_results = data.get('search_results', [])
                
                # Calculate sponsored ads pressure (analyze up to 20 results)
                results_to_analyze = search_results[:20] if len(search_results) > 20 else search_results
                sponsored_count = sum(1 for item in results_to_analyze if item.get('sponsored', False))
                total_count = len(results_to_analyze)
                sponsored_ratio = sponsored_count / total_count if total_count > 0 else 0
                
                # Determine ad pressure level
                if sponsored_ratio < 0.2:
                    ad_pressure_level = "Low"
                elif sponsored_ratio <= 0.5:
                    ad_pressure_level = "Medium"
                else:
                    ad_pressure_level = "High"
                
                print(f"Sponsored Ads Analysis: {sponsored_count}/{total_count} sponsored results ({sponsored_ratio:.1%}) - {ad_pressure_level} Ad Pressure")
                
                products = []
                for item in search_results:
                    # Extract brand information properly
                    brand_info = item.get('brand', {})
                    brand_name = ''
                    
                    # Handle different brand formats in the response
                    if isinstance(brand_info, dict):
                        brand_name = brand_info.get('name', '')
                    elif isinstance(brand_info, str):
                        brand_name = brand_info
                        
                    # Extract price information
                    price_info = item.get('price', {})
                    price_value = 0
                    
                    if isinstance(price_info, dict):
                        price_value = float(price_info.get('value', 0))
                    
                    # Check if this product is sponsored
                    is_sponsored = item.get('sponsored', False)
                    
                    # Create product dictionary with all necessary fields
                    product = {
                        "asin": item.get('asin', ''),
                        "title": item.get('title', ''),
                        "brand": brand_name,
                        "price": price_value,
                        "category": item.get('categories', [{}])[0].get('name', '') if item.get('categories') else '',
                        "image_url": item.get('image', ''),
                        "is_sponsored": is_sponsored,
                        "ad_pressure_level": ad_pressure_level,
                        "sponsored_ratio": sponsored_ratio
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
                'include_data': 'ratings,pricing,bestsellers_rank,brand,offers,buybox_winner,also_bought,sponsored_products'
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
                
                # Get brand information
                # Sometimes brand is a string and sometimes it's a dict with a name field
                brand = product.get('brand', '')
                if isinstance(brand, dict):
                    brand = brand.get('name', '')
                
                # Get best seller ranks - both overall and category-specific
                best_seller_rank = 999999
                category_ranks = []
                bestseller_ranks = product.get('bestsellers_rank', [])
                
                if bestseller_ranks and len(bestseller_ranks) > 0:
                    # Parse all category ranks
                    for rank_entry in bestseller_ranks:
                        rank = rank_entry.get('rank', 999999)
                        category = rank_entry.get('category', 'Unknown Category')
                        
                        # Store each category with its rank
                        category_ranks.append({
                            'rank': rank,
                            'category': category
                        })
                        
                        # Use the best (lowest) rank as the overall rank
                        if rank < best_seller_rank:
                            best_seller_rank = rank
                
                # Extract seller information for competition analysis
                offers = product.get('offers', [])
                marketplace_sellers = []
                
                # Extract marketplace sellers from offers data
                if isinstance(offers, list) and len(offers) > 0:
                    for offer in offers:
                        seller = offer.get('merchant', {})
                        if isinstance(seller, dict):
                            seller_name = seller.get('name', 'Unknown Seller')
                            if seller_name not in marketplace_sellers:
                                marketplace_sellers.append(seller_name)
                
                # Get buybox winner information
                buybox_winner = product.get('buybox_winner', {})
                
                # Determine competition level based on sellers and reviews
                competition_level, competition_details = self.determine_competition_level({
                    'review_count': review_count,
                    'offers': offers,
                    'marketplace_sellers': marketplace_sellers,
                    'buybox_winner': buybox_winner
                })
                
                # Analyze sponsored ad pressure
                ad_pressure_score = 0
                ad_pressure_details = []
                
                # Check if this product is sponsored itself
                is_product_sponsored = product.get('sponsored', False)
                if is_product_sponsored:
                    ad_pressure_score += 1
                    ad_pressure_details.append("Product listing is sponsored")
                
                # Count related sponsored products
                sponsored_products = product.get('sponsored_products', [])
                sponsored_count = len(sponsored_products)
                if sponsored_count > 5:
                    ad_pressure_score += 1
                    ad_pressure_details.append(f"Page shows {sponsored_count} sponsored products")
                
                # Get ad pressure level from search results if available
                ad_pressure_level = product.get('ad_pressure_level', None)
                sponsored_ratio = product.get('sponsored_ratio', None)
                
                # If we're looking at a product detail that wasn't from our search results
                # Use the sponsored products to estimate ad pressure
                if ad_pressure_level is None:
                    # Look at competitors who might be sponsoring ads
                    if sponsored_count == 0:
                        ad_pressure_level = "Low"
                    elif sponsored_count <= 5:
                        ad_pressure_level = "Medium"
                    else:
                        ad_pressure_level = "High"
                    
                # Modify ad pressure level based on additional signals
                if ad_pressure_score >= 2:
                    ad_pressure_level = "High"
                elif ad_pressure_score == 1 and ad_pressure_level != "High":
                    # Bump up one level
                    if ad_pressure_level == "Low":
                        ad_pressure_level = "Medium"
                    elif ad_pressure_level == "Medium":
                        ad_pressure_level = "High"
                
                # Estimate wholesale price (typically 50-60% of retail)
                # This is an estimation - in reality, you'd need supplier data
                wholesale_price = round(retail_price * 0.55, 2)
                
                # Calculate profit margin
                if retail_price > 0 and wholesale_price > 0:
                    profit_margin = ((retail_price - wholesale_price) / retail_price) * 100
                else:
                    profit_margin = 0
                
                # Get the Amazon URL
                amazon_link = f"https://www.amazon.com/dp/{asin}"
                
                return {
                    "brand": brand,
                    "wholesale_price": wholesale_price,
                    "amazon_link": amazon_link,
                    "rating": rating,
                    "review_count": review_count,
                    "best_seller_rank": best_seller_rank,
                    "category_ranks": category_ranks,
                    "profit_margin": round(profit_margin, 2),
                    "marketplace_sellers": marketplace_sellers,
                    "seller_count": len(marketplace_sellers),
                    "competition_level": competition_level,
                    "competition_details": competition_details,
                    "is_sponsored": is_product_sponsored,
                    "sponsored_count": sponsored_count,
                    "ad_pressure_level": ad_pressure_level,
                    "ad_pressure_details": ad_pressure_details,
                    "ad_pressure_score": ad_pressure_score
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
            'profit_margin': 0.25,   # Profit margin
            'ad_pressure': 0.15      # Ad pressure (inverse)
        }
        
        # Get values (with defaults if missing)
        rating = product.get('rating', 0) 
        review_count = min(product.get('review_count', 0) / 5000, 1)  # Normalize to 0-1
        best_seller_rank = product.get('best_seller_rank', 1000)
        rank_score = 1 - min(best_seller_rank / 100, 1)  # Normalize and invert
        profit_margin = min(product.get('profit_margin', 0) / 100, 1)  # Normalize to 0-1
        
        # Calculate ad pressure score (inverse - lower ad pressure is better)
        ad_pressure_level = product.get('ad_pressure_level', 'Medium')
        ad_pressure_score = 0
        if ad_pressure_level == "Low":
            ad_pressure_score = 1.0  # Best score
        elif ad_pressure_level == "Medium":
            ad_pressure_score = 0.5  # Medium score
        else:  # High
            ad_pressure_score = 0.1  # Worst score
        
        # Calculate weighted score
        score = (
            weights['rating'] * (rating / 5) +
            weights['review_count'] * review_count +
            weights['rank'] * rank_score +
            weights['profit_margin'] * profit_margin +
            weights['ad_pressure'] * ad_pressure_score
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
                'asin': asin,
                'include_data': 'ratings,pricing,bestsellers_rank,brand,categories,offers,buybox_winner,sponsored_products'
            }
            
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                rf_product = data.get('product', {})
                
                # Extract brand information correctly
                brand_info = rf_product.get('brand', '')
                brand_name = ''
                
                # Handle different brand formats
                if isinstance(brand_info, dict):
                    brand_name = brand_info.get('name', '')
                elif isinstance(brand_info, str):
                    brand_name = brand_info
                
                # Extract price information
                retail_price = 0
                buybox = rf_product.get('buybox_winner', {})
                
                if isinstance(buybox, dict):
                    price_info = buybox.get('price', {})
                    if isinstance(price_info, dict):
                        retail_price = float(price_info.get('value', 0))
                
                # Extract category information
                category = 'Uncategorized'
                categories = rf_product.get('categories', [])
                if categories and len(categories) > 0:
                    category = categories[0].get('name', 'Uncategorized')
                
                # Extract image URL
                image_url = ''
                main_image = rf_product.get('main_image', {})
                if isinstance(main_image, dict):
                    image_url = main_image.get('link', '')
                
                # Extract seller information for competition analysis
                offers = rf_product.get('offers', [])
                marketplace_sellers = []
                
                # Extract marketplace sellers from offers data
                if isinstance(offers, list) and len(offers) > 0:
                    for offer in offers:
                        seller = offer.get('merchant', {})
                        if isinstance(seller, dict):
                            seller_name = seller.get('name', 'Unknown Seller')
                            if seller_name not in marketplace_sellers:
                                marketplace_sellers.append(seller_name)
                
                # Check if product is sponsored
                is_sponsored = rf_product.get('sponsored', False)
                
                # Count related sponsored products
                sponsored_products = rf_product.get('sponsored_products', [])
                sponsored_count = len(sponsored_products) if sponsored_products else 0
                
                # Extract basic product data
                product = {
                    "asin": asin,
                    "title": rf_product.get('title', ''),
                    "brand": brand_name,
                    "price": retail_price,
                    "category": category,
                    "image_url": image_url,
                    "marketplace_sellers": marketplace_sellers,
                    "seller_count": len(marketplace_sellers),
                    "is_sponsored": is_sponsored,
                    "sponsored_count": sponsored_count
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
            
    def _get_product_reviews(self, asin):
        """
        Get product reviews from Rainforest API
        
        Args:
            asin (str): The Amazon ASIN for the product
            
        Returns:
            list: A list of review texts or empty list if no reviews found/error
        """
        try:
            print(f"Getting reviews for ASIN: {asin}")
            
            # Build the request parameters
            params = {
                'api_key': self.rainforest_api_key,
                'type': 'reviews',
                'amazon_domain': 'amazon.com',
                'asin': asin,
                'filter_by_star': 'all_stars',
                'sort_by': 'most_recent',
                'language': 'en_US',
                'review_formats': 'default_format',
                'page': '1'
            }
            
            # Make the request
            response = requests.get('https://api.rainforestapi.com/request', params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                reviews = []
                review_data = data.get('reviews', [])
                
                # Get up to 20 reviews to avoid excessive API usage
                for review in review_data[:20]:
                    title = review.get('title', '')
                    body = review.get('body', '')
                    rating = review.get('rating', 0)
                    
                    # Combine title and body for a complete review text
                    review_text = f"{title}. {body}"
                    # Add rating information
                    review_info = {
                        "text": review_text,
                        "rating": rating
                    }
                    reviews.append(review_info)
                
                return reviews
            else:
                print(f"Error getting reviews from Rainforest: {response.text}")
                return []
            
        except Exception as e:
            print(f"Error getting product reviews: {e}")
            return []
    
    def _analyze_reviews_for_issues(self, reviews):
        """
        Analyze product reviews to identify common complaints and improvement opportunities
        
        Args:
            reviews (list): List of review dictionaries with 'text' and 'rating'
            
        Returns:
            str: Summary of issues and suggested improvements
        """
        try:
            if not reviews:
                return ""
            
            # Prepare the reviews for analysis
            reviews_text = ""
            for i, review in enumerate(reviews, 1):
                reviews_text += f"Review {i} (Rating: {review['rating']}/5): {review['text']}\n\n"
            
            prompt = f"""
            Given the following product reviews, summarize the top customer complaints and suggest 3 improvements 
            that could make the product better:
            
            {reviews_text}
            
            Keep your response to under 100 words total, focusing only on the most actionable insights.
            Format your response in two sections:
            1. Common Complaints: Briefly list key issues mentioned by customers
            2. Suggested Improvements: List 3 specific ways to improve the product
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You analyze product reviews to identify improvements."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.5
            )
            
            analysis = response.choices[0].message.content.strip()
            return analysis
            
        except Exception as e:
            print(f"Error analyzing reviews: {e}")
            return ""
    
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
        score = product.get('score', 0)
        
        # Get competition and seller information
        competition_level = product.get('competition_level', 'Unknown')
        competition_details = product.get('competition_details', '')
        seller_count = product.get('seller_count', 0)
        marketplace_sellers = product.get('marketplace_sellers', [])
        
        # Get sponsored ads and ad pressure information
        ad_pressure_level = product.get('ad_pressure_level', 'Unknown')
        ad_pressure_details = product.get('ad_pressure_details', [])
        is_sponsored = product.get('is_sponsored', False)
        sponsored_count = product.get('sponsored_count', 0)
        
        # Get category-specific rankings
        category_ranks = product.get('category_ranks', [])
        
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
        analysis += f"- **Profit Per Unit:** ${profit_per_unit:.2f}\n\n"
        
        # Create profitability projection grid
        analysis += "## Profitability Projection Table\n\n"
        
        # Define unit sales scenarios
        units_scenarios = [10, 25, 50, 100, 250, 500]
        
        # Create the table header
        analysis += "| Units Sold per Month | Monthly Profit |\n"
        analysis += "|----------------------|----------------|\n"
        
        # Add rows for each scenario
        for units in units_scenarios:
            monthly_profit = units * profit_per_unit
            analysis += f"| {units} units | ${monthly_profit:.2f} |\n"
        
        # Add disclaimer note
        analysis += "\n*These are hypothetical projections based on manual unit sales assumptions. Actual results depend on real market demand and competition.*\n\n"
        
        # Market analysis
        analysis += "## Market Performance\n"
        analysis += f"- **Rating:** {rating}/5 ({review_count} reviews)\n"
        analysis += f"- **Best Seller Rank:** {best_seller_rank}\n"
        
        # Add category-specific rankings if available
        if category_ranks and len(category_ranks) > 0:
            analysis += "- **Category Rankings:**\n"
            for i, rank_info in enumerate(category_ranks, 1):
                category_name = rank_info.get('category', 'Unknown Category')
                category_rank = rank_info.get('rank', 'N/A')
                analysis += f"  - **{category_name}:** #{category_rank}\n"
        
        # Add competition analysis
        analysis += "\n## Competition Analysis\n"
        analysis += f"- **Competition Level:** {competition_level}\n"
        if competition_details:
            analysis += f"- **Competition Details:** {competition_details}\n"
        
        # Add seller information if available
        if seller_count > 0:
            analysis += f"- **Number of Sellers:** {seller_count}\n"
            
            # List major sellers (up to 5)
            if marketplace_sellers and len(marketplace_sellers) > 0:
                top_sellers = marketplace_sellers[:5]
                seller_list = ", ".join(top_sellers)
                
                if len(marketplace_sellers) > 5:
                    seller_list += f" and {len(marketplace_sellers) - 5} more"
                    
                analysis += f"- **Major Sellers:** {seller_list}\n"
        
        # Add sponsored ads pressure analysis
        analysis += "\n## Sponsored Ads Pressure\n"
        analysis += f"- **Ad Pressure Level:** {ad_pressure_level}\n"
        
        # Add warning for high ad pressure
        if ad_pressure_level == "High":
            analysis += "\n⚠️ **High ad saturation detected. Launching in this market may require significant advertising spend to compete.**\n"
        
        # Add details about sponsored ads if available
        if is_sponsored:
            analysis += "- This product listing is sponsored\n"
        if sponsored_count > 0:
            analysis += f"- Found {sponsored_count} sponsored product ads related to this item\n"
        if ad_pressure_details and len(ad_pressure_details) > 0:
            for detail in ad_pressure_details:
                analysis += f"- {detail}\n"
        
        # Get and analyze customer reviews if ASIN is available
        if asin:
            reviews = self._get_product_reviews(asin)
            if reviews:
                review_analysis = self._analyze_reviews_for_issues(reviews)
                if review_analysis:
                    analysis += "\n## Customer Feedback Insights\n"
                    analysis += review_analysis + "\n\n"
        
        # Determine viability level based on score and competition
        viability = "Low"
        if score >= 70 and competition_level in ["Low", "Medium"]:
            viability = "High"
        elif (score >= 70 and competition_level == "High") or (score >= 40 and competition_level in ["Low", "Medium"]):
            viability = "Medium"
            
        analysis += f"\n## Overall E-commerce Viability: {viability}\n\n"
        
        # Generate risk assessment based on competition and reviews
        risk_level = "Unknown"
        risk_details = ""
        
        if competition_level == "High" and review_count >= 1000:
            risk_level = "High"
            risk_details = "Saturated market with established players"
        elif competition_level == "Medium" or (competition_level == "High" and review_count < 1000):
            risk_level = "Medium"
            risk_details = "Competitive market with room for differentiation"
        elif competition_level == "Low" and review_count > 0:
            risk_level = "Low"
            risk_details = "Relatively open market with limited competition"
        elif review_count == 0:
            risk_level = "High"
            risk_details = "Unproven market without review validation"
            
        analysis += f"- **Risk Level:** {risk_level} - {risk_details}\n\n"
        
        # Generate passion product ideas
        passion_ideas = self._generate_passion_product_ideas(title, category)
        if passion_ideas:
            analysis += "## Passion Product Ideas\n"
            analysis += passion_ideas + "\n\n"
        
        # Final recommendation
        analysis += "## Recommendation\n"
        if score >= 70 and competition_level in ["Low", "Medium"]:
            analysis += "- **Strong potential** for direct selling or creating passion products\n"
            analysis += "- Consider starting with small inventory test orders\n"
            analysis += "- High profit margin and proven sales history make this a promising opportunity\n"
        elif score >= 40 or competition_level == "Low":
            analysis += "- **Moderate potential** requires careful consideration\n"
            analysis += "- Explore ways to differentiate or add value through passion products\n"
            analysis += "- Test market with minimal investment before scaling\n"
        else:
            analysis += "- **Limited direct selling potential**\n"
            analysis += "- Consider only if you have unique improvements or market positioning\n"
            analysis += "- High risk relative to potential reward\n"
        
        # Add additional recommendation based on ad pressure
        if ad_pressure_level == "High":
            analysis += "- **Consider advertising costs** in your business model as this market has high ad saturation\n"
        
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
    
    def parse_query_filters(self, query):
        """
        Extract filtering criteria from the user's natural language query
        
        Args:
            query (str): The user's search query
            
        Returns:
            dict: Dictionary with filter criteria
        """
        try:
            print(f"Parsing filters from query: {query}")
            
            # Initialize default filter values
            filters = {
                'min_margin': None,
                'max_price': None,
                'min_rating': None,
                'max_reviews': None,
                'category': None
            }
            
            # Use OpenAI to extract structured filter information
            prompt = f"""
            Extract specific product search filters from this query: "{query}"
            
            Format your response as a JSON object with these fields:
            - min_margin: Minimum profit margin as a number (e.g., 50 for 50%)
            - max_price: Maximum product price as a number without $ (e.g., 30)
            - min_rating: Minimum star rating as a number (e.g., 4)
            - max_reviews: Maximum number of reviews as a number (e.g., 500)
            - category: Product category name as a string (e.g., "bathroom")
            
            Use null for any filters not specified in the query.
            
            Examples:
            "Find bathroom products with at least 50% margin" → {{"min_margin": 50, "max_price": null, "min_rating": null, "max_reviews": null, "category": "bathroom"}}
            
            "Show me kitchen gadgets under $30 with at least 4 stars" → {{"min_margin": null, "max_price": 30, "min_rating": 4, "max_reviews": null, "category": "kitchen"}}
            
            "Trending bathroom products with less than 500 reviews" → {{"min_margin": null, "max_price": null, "min_rating": null, "max_reviews": 500, "category": "bathroom"}}
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You extract structured product filter information from queries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                response_format={"type": "json_object"}
            )
            
            # Parse the response into a Python dictionary
            extracted_filters = json.loads(response.choices[0].message.content)
            
            # Update our filters dictionary with the extracted values
            for key, value in extracted_filters.items():
                if value is not None:
                    filters[key] = value
            
            # Fallback parsing for common filter phrases (in case OpenAI struggles)
            if filters['min_margin'] is None and "margin" in query.lower():
                # Look for patterns like "50% margin" or "margin of 50%"
                import re
                margin_match = re.search(r'(\d+)%\s+margin|margin\s+of\s+(\d+)%', query.lower())
                if margin_match:
                    margin_val = margin_match.group(1) or margin_match.group(2)
                    filters['min_margin'] = int(margin_val)
            
            if filters['max_price'] is None and ("under" in query.lower() or "less than" in query.lower()):
                # Look for patterns like "under $30" or "less than $50"
                import re
                price_match = re.search(r'under\s+\$?(\d+)|less than\s+\$?(\d+)', query.lower())
                if price_match:
                    price_val = price_match.group(1) or price_match.group(2)
                    filters['max_price'] = int(price_val)
            
            print(f"Extracted filters: {filters}")
            return filters
            
        except Exception as e:
            print(f"Error parsing query filters: {e}")
            return {
                'min_margin': None,
                'max_price': None,
                'min_rating': None,
                'max_reviews': None,
                'category': None
            }
    
    def determine_competition_level(self, product_data):
        """
        Determine the competition level based on review count and number of sellers
        
        Args:
            product_data (dict): The product data containing review count and seller info
            
        Returns:
            tuple: (competition_level, competition_details) - the competition level and details
        """
        try:
            review_count = product_data.get('review_count', 0)
            
            # Get the number of sellers if available
            seller_count = 0
            buybox_winner = product_data.get('buybox_winner', {})
            
            # First check offers data - this contains all sellers
            offers = product_data.get('offers', [])
            if offers and isinstance(offers, list):
                seller_count = len(offers)
            # If no offers data, check if marketplace_sellers is available
            elif product_data.get('marketplace_sellers') and isinstance(product_data.get('marketplace_sellers'), list):
                seller_count = len(product_data.get('marketplace_sellers', []))
            # If we at least have buybox winner, that's one seller
            elif buybox_winner and isinstance(buybox_winner, dict):
                seller_count = 1
                # Check if fulfillment is by Amazon or third party
                if buybox_winner.get('fulfilled_by') == 'Amazon':
                    seller_count += 1  # Consider Amazon as an additional seller
            
            # Determine competition level based on number of sellers
            if seller_count == 0:
                # Fall back to review count if no seller data is available
                if review_count == 0:
                    competition_level = "Unknown"
                    competition_details = "No review or seller data available"
                elif review_count < 500:
                    competition_level = "Low"
                    competition_details = f"Only {review_count} reviews, likely new market"
                elif review_count < 1000:
                    competition_level = "Medium"
                    competition_details = f"{review_count} reviews indicate established competition"
                else:
                    competition_level = "High"
                    competition_details = f"High review count ({review_count}) indicates mature market"
            else:
                # Determine based on seller count
                if seller_count <= 2:
                    competition_level = "Low"
                    competition_details = f"Only {seller_count} sellers in the market"
                elif seller_count <= 5:
                    competition_level = "Medium"
                    competition_details = f"{seller_count} sellers competing in this market"
                else:
                    competition_level = "High"
                    competition_details = f"Crowded market with {seller_count} active sellers"
                
                # Add review count context to the competition details
                if review_count > 0:
                    competition_details += f" with {review_count} product reviews"
            
            return competition_level, competition_details
            
        except Exception as e:
            print(f"Error determining competition level: {e}")
            return "Unknown", "Error analyzing competition data"
    
    def _apply_filters(self, products, filters):
        """
        Apply parsed filters to product list
        
        Args:
            products (list): List of product dictionaries
            filters (dict): Dictionary of filter criteria
            
        Returns:
            list: Filtered list of products
        """
        if not products:
            return []
        
        filtered = []
        
        # Extract filters
        min_margin = filters.get('min_margin')
        max_price = filters.get('max_price')
        min_rating = filters.get('min_rating')
        max_reviews = filters.get('max_reviews')
        
        print(f"Applying filters: {filters}")
        
        for product in products:
            # Check if product meets all filter criteria
            include_product = True
            
            # Apply margin filter if specified
            if min_margin is not None and product.get('profit_margin', 0) < min_margin:
                include_product = False
            
            # Apply price filter if specified
            if max_price is not None and product.get('price', float('inf')) > max_price:
                include_product = False
            
            # Apply rating filter if specified
            if min_rating is not None and product.get('rating', 0) < min_rating:
                include_product = False
            
            # Apply reviews filter if specified
            if max_reviews is not None and product.get('review_count', float('inf')) > max_reviews:
                include_product = False
            
            if include_product:
                filtered.append(product)
        
        print(f"Filtered from {len(products)} to {len(filtered)} products")
        
        # If all products were filtered out, return a few of the original products
        # This ensures the user gets some results even if no products match all criteria
        if not filtered and products:
            print("All products filtered out, returning top products from original list")
            products.sort(key=lambda x: x.get('score', 0), reverse=True)
            return products[:min(3, len(products))]
        
        return filtered 