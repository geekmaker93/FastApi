import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class BBCNewsService:
    """
    BBC News RSS Feed Parser
    Fetches and parses BBC News RSS feeds
    """
    
    # BBC News RSS Feed URLs
    BBC_NEWS_FEEDS = {
        'top_stories': 'http://feeds.bbci.co.uk/news/rss.xml',
        'world': 'http://feeds.bbci.co.uk/news/world/rss.xml',
        'uk': 'http://feeds.bbci.co.uk/news/uk/rss.xml',
        'business': 'http://feeds.bbci.co.uk/news/business/rss.xml',
        'technology': 'http://feeds.bbci.co.uk/news/technology/rss.xml',
        'science_environment': 'http://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
        'entertainment': 'http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml',
        'health': 'http://feeds.bbci.co.uk/news/health/rss.xml',
        'politics': 'http://feeds.bbci.co.uk/news/politics/rss.xml',
        'education': 'http://feeds.bbci.co.uk/news/education/rss.xml',
        'england': 'http://feeds.bbci.co.uk/news/england/rss.xml',
        'scotland': 'http://feeds.bbci.co.uk/news/scotland/rss.xml',
        'wales': 'http://feeds.bbci.co.uk/news/wales/rss.xml',
        'northern_ireland': 'http://feeds.bbci.co.uk/news/northern_ireland/rss.xml',
        'world_africa': 'http://feeds.bbci.co.uk/news/world/africa/rss.xml',
        'world_asia': 'http://feeds.bbci.co.uk/news/world/asia/rss.xml',
        'world_europe': 'http://feeds.bbci.co.uk/news/world/europe/rss.xml',
        'world_latin_america': 'http://feeds.bbci.co.uk/news/world/latin_america/rss.xml',
        'world_middle_east': 'http://feeds.bbci.co.uk/news/world/middle_east/rss.xml',
        'world_us_canada': 'http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml',
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 5  # Reduced from 10 to 5 seconds
        # Simple in-memory cache with timestamp
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._cache_duration = timedelta(minutes=10)  # Cache for 10 minutes
    
    def get_news(self, category: str = 'top_stories', limit: int = 100) -> Dict:
        """
        Fetch BBC News articles from RSS feed
        
        Args:
            category: News category (top_stories, world, business, etc.)
            limit: Maximum number of articles to return
        
        Returns:
            Dictionary with news articles
        """
        try:
            if category not in self.BBC_NEWS_FEEDS:
                raise ValueError(f"Invalid category. Available: {list(self.BBC_NEWS_FEEDS.keys())}")
            
            url = self.BBC_NEWS_FEEDS[category]
            # Bound each upstream fetch to keep mobile requests responsive.
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            
            return self._parse_rss(response.text, category, limit)
        except Exception as e:
            raise ValueError(f"Failed to fetch BBC News: {str(e)}")
    
    def _parse_rss(self, rss_content: str, category: str, limit: int) -> Dict:
        """Parse BBC News RSS XML content"""
        try:
            root = ET.fromstring(rss_content)
            
            # Get channel info
            channel = root.find('channel')
            if channel is None:
                raise ValueError("Invalid RSS format: no channel found")
            
            feed_title = channel.findtext('title', 'BBC News')
            feed_description = channel.findtext('description', '')
            feed_link = channel.findtext('link', '')
            
            # Get news items
            items = channel.findall('item')[:limit]
            
            articles = []
            for item in items:
                article = self._parse_article(item)
                if article:
                    articles.append(article)
            
            return {
                'source': 'BBC News RSS',
                'category': category,
                'feed_title': feed_title,
                'feed_description': feed_description,
                'feed_link': feed_link,
                'total_articles': len(articles),
                'articles': articles,
                'timestamp': datetime.now().isoformat()
            }
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse RSS XML: {str(e)}")
    
    def _parse_article(self, item: ET.Element) -> Optional[Dict]:
        """Parse individual news article from RSS item"""
        try:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            description = item.findtext('description', '')
            pub_date = item.findtext('pubDate', '')
            
            # Get media thumbnail if available
            thumbnail = None
            media_thumbnail = item.find('{http://search.yahoo.com/mrss/}thumbnail')
            if media_thumbnail is not None:
                thumbnail = media_thumbnail.get('url')
                # BBC uses URLs like: 
                # https://ichef.bbci.co.uk/ace/standard/240/...
                # https://ichef.bbci.co.uk/news/144x81_...
                # Upgrade to higher resolution for better quality
                if thumbnail and 'ichef.bbci.co.uk' in thumbnail:
                    # Replace /240/ with /640/ for higher resolution
                    if '/ace/standard/240/' in thumbnail:
                        thumbnail = thumbnail.replace('/ace/standard/240/', '/ace/standard/640/')
                    # Also handle news format: 144x81 -> 640x360
                    elif re.search(r'/news/\d+x\d+_', thumbnail):
                        thumbnail = re.sub(r'/news/\d+x\d+_', '/news/640x360_', thumbnail)
            
            # Clean up description (remove HTML tags)
            clean_description = re.sub(r'<[^>]+>', '', description)
            
            # Parse pub date
            published_date = pub_date
            try:
                # Try to parse RFC 822 date format
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub_date)
                published_date = dt.isoformat()
            except:
                pass
            
            return {
                'title': title,
                'link': link,
                'description': clean_description,
                'published': published_date,
                'image_url': thumbnail,
                'thumbnail': thumbnail  # Keep for backwards compatibility
            }
        except Exception as e:
            # Skip articles that fail to parse
            return None
    
    def search_news(self, keyword: str, category: str = 'top_stories', limit: int = 20) -> List[Dict]:
        """
        Search for news articles containing a keyword
        
        Args:
            keyword: Search term
            category: News category to search in
            limit: Maximum results
        
        Returns:
            List of matching articles
        """
        news_data = self.get_news(category, limit=100)  # Get more to search through
        
        keyword_lower = keyword.lower()
        matching_articles = []
        
        for article in news_data['articles']:
            if (keyword_lower in article['title'].lower() or 
                keyword_lower in article['description'].lower()):
                matching_articles.append(article)
                if len(matching_articles) >= limit:
                    break
        
        return matching_articles
    
    def get_all_news_fast(self, categories: List[str], limit_per_category: int = 30) -> List[Dict]:
        """
        Fetch news from multiple categories in parallel for speed
        Returns deduplicated list of articles
        """
        all_articles = []
        seen_links = set()
        
        def fetch_category(category):
            """Helper to fetch a single category"""
            try:
                # Check cache first
                cache_key = f"{category}_{limit_per_category}"
                cached = self._get_from_cache(cache_key)
                if cached:
                    return cached
                
                news_data = self.get_news(category, limit=limit_per_category)
                articles = news_data.get('articles', [])
                
                # Cache the result
                self._add_to_cache(cache_key, articles)
                return articles
            except:
                return []
        
        # Fetch all categories in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_category = {executor.submit(fetch_category, cat): cat for cat in categories}
            
            for future in as_completed(future_to_category):
                articles = future.result()
                for article in articles:
                    if article and article['link'] not in seen_links:
                        seen_links.add(article['link'])
                        all_articles.append(article)
        
        return all_articles
    
    def _get_from_cache(self, key: str) -> Optional[List[Dict]]:
        """Get articles from cache if still valid"""
        with self._cache_lock:
            if key in self._cache:
                cached_data, timestamp = self._cache[key]
                if datetime.now() - timestamp < self._cache_duration:
                    return cached_data
                else:
                    # Cache expired, remove it
                    del self._cache[key]
        return None
    
    def _add_to_cache(self, key: str, articles: List[Dict]):
        """Add articles to cache with timestamp"""
        with self._cache_lock:
            self._cache[key] = (articles, datetime.now())
    
    def get_available_categories(self) -> Dict:
        """Get list of available news categories"""
        return {
            'categories': list(self.BBC_NEWS_FEEDS.keys()),
            'descriptions': {
                'top_stories': 'Top headlines from BBC News',
                'world': 'International news',
                'uk': 'UK news',
                'business': 'Business and economics news',
                'technology': 'Technology news',
                'science_environment': 'Science and environment news',
                'entertainment': 'Entertainment and arts news',
                'health': 'Health news'
            }
        }


# Singleton instance
bbc_news = BBCNewsService()
