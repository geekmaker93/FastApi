from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
from app.services.bbc_news import bbc_news
from app.services.article_proxy import article_proxy

router = APIRouter(prefix="/news", tags=["news"])


def _build_agriculture_news(limit: int):
    """Build agriculture-focused feed by searching across BBC categories."""
    agriculture_keywords = ['agriculture', 'farm', 'crop', 'farming', 'harvest']
    categories = ['business', 'science_environment', 'world', 'uk']

    all_articles = []
    for cat in categories:
        for keyword in agriculture_keywords:
            articles = bbc_news.search_news(keyword, cat, limit=5)
            all_articles.extend(articles)

    seen_links = set()
    unique_articles = []
    for article in all_articles:
        link = article.get('link')
        if link and link not in seen_links:
            seen_links.add(link)
            unique_articles.append(article)
            if len(unique_articles) >= limit:
                break

    return {
        'source': 'BBC News RSS',
        'category': 'agriculture',
        'total_articles': len(unique_articles),
        'articles': unique_articles,
        'items': unique_articles,
        'timestamp': datetime.now().isoformat()
    }


@router.get("/")
def get_news(
    category: Optional[str] = Query('top_stories', description="News category"),
    limit: int = Query(100, ge=1, le=200, description="Number of articles to return (default 100, max 200)")
):
    """
    Get BBC News articles
    
    Default: Top Stories (20 articles)
    
    Examples:
    - /news/ - Top stories
    - /news/?category=business&limit=10 - Business news (10 articles)
    - /news/?category=technology - Technology news
    
    Available categories: top_stories, world, uk, business, technology, 
                         science_environment, entertainment, health
    """
    try:
        effective_limit = max(limit, 20)
        requested_category = (category or 'top_stories').strip().lower()
        if requested_category in {'all', ''}:
            requested_category = 'top_stories'
        if requested_category in {'agriculture', 'agri'}:
            news_data = _build_agriculture_news(effective_limit)
        else:
            news_data = bbc_news.get_news(requested_category, effective_limit)
        # Keep both keys for broad client compatibility
        news_data['items'] = news_data.get('articles', [])
        return news_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch news: {str(e)}")


@router.get("/categories")
def get_news_categories():
    """Get list of available BBC News categories"""
    return bbc_news.get_available_categories()


@router.get("/search")
def search_news(
    keyword: str = Query(..., description="Search term"),
    category: Optional[str] = Query('top_stories', description="Category to search in"),
    limit: int = Query(100, ge=1, le=200, description="Max results")
):
    """
    Search BBC News articles by keyword
    
    Examples:
    - /news/search?keyword=agriculture
    - /news/search?keyword=climate&category=science_environment
    - /news/search?keyword=economy&category=business&limit=10
    """
    try:
        articles = bbc_news.search_news(keyword, category, limit)
        return {
            'source': 'BBC News RSS',
            'keyword': keyword,
            'category': category,
            'total_results': len(articles),
            'items': articles
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/business")
def get_business_news(limit: int = Query(100, ge=1, le=200)):
    """Get BBC Business news (shortcut endpoint)"""
    try:
        news_data = bbc_news.get_news('business', limit)
        news_data['items'] = news_data.get('articles', [])
        return news_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/technology")
def get_technology_news(limit: int = Query(100, ge=1, le=200)):
    """Get BBC Technology news (shortcut endpoint)"""
    try:
        news_data = bbc_news.get_news('technology', limit)
        news_data['items'] = news_data.get('articles', [])
        return news_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agriculture")
def get_agriculture_news(limit: int = Query(100, ge=1, le=200)):
    """Get agriculture-related news (searches across categories)"""
    try:
        return _build_agriculture_news(max(limit, 20))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
def get_all_news(
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0, description="Number of articles to skip (for pagination)"),
    category: Optional[str] = Query('all', description="News category filter")
):
    """
    Get news from ALL BBC categories combined (maximum articles with pagination)
    Uses parallel fetching and caching for fast performance
    
    For infinite scroll:
    - First load: /news/all?limit=50&offset=0
    - Next load: /news/all?limit=50&offset=50
    - Next load: /news/all?limit=50&offset=100
    """
    try:
        effective_limit = max(limit, 20)
        requested_category = (category or 'all').strip().lower()

        if requested_category in {'agriculture', 'agri'}:
            all_articles = _build_agriculture_news(500).get('items', [])
        else:
            # Fetch from ALL available categories in parallel
            categories = [
                'top_stories', 'world', 'business', 'technology', 'science_environment',
                'health', 'politics', 'education', 'entertainment',
                'england', 'scotland', 'wales', 'northern_ireland',
                'world_africa', 'world_asia', 'world_europe', 'world_latin_america',
                'world_middle_east', 'world_us_canada', 'uk'
            ]

            # Use fast parallel fetching (30 articles per category, cached for 10 min)
            all_articles = bbc_news.get_all_news_fast(categories, limit_per_category=30)
        
        # Apply offset and limit
        paginated_articles = all_articles[offset:offset + effective_limit]
        
        return {
            'source': 'BBC News RSS (All Categories)',
            'category': requested_category,
            'total_articles': len(all_articles),
            'returned_articles': len(paginated_articles),
            'offset': offset,
            'limit': effective_limit,
            'has_more': offset + effective_limit < len(all_articles),
            'items': paginated_articles,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{article_id}")
def get_article_detail(article_id: str):
    """
    Get article details for display in app
    
    Article IDs are BBC article codes extracted from URLs
    Example: /news/cd032xnm804o
    
    This avoids loading external links and instead provides
    article content for in-app display
    """
    try:
        # This is a proxy endpoint that returns article metadata
        # In production, you could scrape/cache article content
        return {
            'source': 'BBC News',
            'article_id': article_id,
            'message': 'Use the article link property to open in browser',
            'url': f'https://www.bbc.com/news/articles/{article_id}'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proxy/content")
def get_article_proxy(url: str = Query(..., description="Full BBC article URL")):
    """
    Proxy endpoint to fetch BBC article content through the backend
    This works around WebView restrictions
    
    Example: /news/proxy/content?url=https://www.bbc.com/news/articles/cd032xnm804o
    """
    try:
        if not url.startswith('https://www.bbc.com/') and not url.startswith('http://www.bbc.com/'):
            raise ValueError("Only BBC URLs allowed")
        
        article_data = article_proxy.get_article_content(url)
        return {
            'source': 'BBC News (Proxied)',
            'article': article_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch article: {str(e)}")


@router.get("/image/highres")
def get_highres_image(link: str = Query(..., description="BBC article link")):
    """
    Extract high-resolution image from BBC article page
    This improves image quality over RSS thumbnails
    
    Example: /news/image/highres?link=https://www.bbc.com/news/articles/cd032xnm804o
    """
    try:
        if not link.startswith('https://www.bbc.com/') and not link.startswith('http://www.bbc.com/'):
            raise HTTPException(status_code=400, detail="Only BBC URLs allowed")
        
        # Fetch the article page to extract high-res image
        try:
            article_data = article_proxy.get_article_content(link)
            if article_data.get('image_url'):
                return {
                    'image_url': article_data['image_url'],
                    'title': article_data.get('title'),
                    'link': link
                }
        except:
            pass
        
        # If extraction fails, return low-res RSS image
        raise HTTPException(status_code=404, detail="High-res image not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch image: {str(e)}")
