import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
import re

class ArticleProxyService:
    """
    Proxy BBC articles through the backend to avoid WebView restrictions
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.session.timeout = 10
    
    def get_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch BBC article and extract content
        Returns article with title, content, published date, image
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract article data
            article_data = self._extract_article_data(soup, url)
            return article_data
            
        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch article: {str(e)}")
    
    def _extract_article_data(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract article content from BBC HTML"""
        
        # Try to get title
        title = None
        title_tag = soup.find('h1')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Try to get main image
        image_url = None
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            image_url = img_tag.get('src')
            # Fix relative URLs
            if image_url.startswith('//'):
                image_url = 'https:' + image_url
        
        # Try to get publish date
        published = None
        time_tag = soup.find('time')
        if time_tag:
            published = time_tag.get('datetime') or time_tag.get_text(strip=True)
        
        # Extract article content/paragraphs
        content_parts = []
        
        # Try BBC article structure
        article_div = soup.find('article')
        if article_div:
            paragraphs = article_div.find_all('p')
            content_parts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        
        if not content_parts:
            # Fallback: get all paragraphs
            all_paragraphs = soup.find_all('p')
            content_parts = [p.get_text(strip=True) for p in all_paragraphs if p.get_text(strip=True)][:10]
        
        content = ' '.join(content_parts)[:5000]  # Limit to 5000 chars
        
        return {
            'url': url,
            'title': title or 'BBC News Article',
            'published': published,
            'image_url': image_url,
            'content': content,
            'is_proxy': True
        }
    
    def get_article_html(self, url: str) -> Optional[str]:
        """
        Get full HTML page for display
        This is for fallback if extraction fails
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Return the full HTML
            return response.text
            
        except Exception as e:
            raise ValueError(f"Failed to fetch article HTML: {str(e)}")


# Singleton instance
article_proxy = ArticleProxyService()
