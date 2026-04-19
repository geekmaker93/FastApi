"""
Web search and external data integration for AI context enrichment.
Provides real-time information from Google and other sources.
"""
import os
import logging
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

# Configuration
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

def search_google_custom(query: str, num_results: int = 3) -> List[Dict[str, Any]]:
    """
    Search using Google Custom Search API.
    
    Setup:
    1. Go to https://developers.google.com/custom-search/v1/overview
    2. Create API key: https://console.cloud.google.com/apis/credentials
    3. Create search engine: https://programmablesearchengine.google.com/
    4. Set environment variables: GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_ENGINE_ID
    
    Returns:
        List of search results with title, snippet, link
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        logger.warning("Google Custom Search not configured (no API key/engine ID)")
        return []
    
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_SEARCH_API_KEY,
            "cx": GOOGLE_SEARCH_ENGINE_ID,
            "q": query,
            "num": num_results,
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("items", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "source": "google_custom_search",
            })
        
        logger.info(f"Google Custom Search returned {len(results)} results for '{query[:50]}'")
        return results
        
    except requests.RequestException as e:
        logger.error(f"Google Custom Search failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Google Custom Search error: {e}")
        return []


def search_serpapi(query: str, num_results: int = 3, location: str = "United States") -> List[Dict[str, Any]]:
    """
    Search using SerpAPI (simplified Google Search API).
    
    Setup:
    1. Sign up at https://serpapi.com/ (free tier: 100 searches/month)
    2. Get API key from dashboard
    3. Set environment variable: SERPAPI_KEY
    
    Returns:
        List of search results with title, snippet, link
    """
    if not SERPAPI_KEY:
        logger.warning("SerpAPI not configured (no API key)")
        return []
    
    try:
        url = "https://serpapi.com/search"
        params = {
            "api_key": SERPAPI_KEY,
            "q": query,
            "num": num_results,
            "location": location,
            "engine": "google",
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "source": "serpapi",
            })
        
        logger.info(f"SerpAPI returned {len(results)} results for '{query[:50]}'")
        return results
        
    except requests.RequestException as e:
        logger.error(f"SerpAPI search failed: {e}")
        return []
    except Exception as e:
        logger.error(f"SerpAPI error: {e}")
        return []


def search_duckduckgo(query: str, num_results: int = 3) -> List[Dict[str, Any]]:
    """
    Search using DuckDuckGo (no API key required, but basic results).
    
    This is a fallback option when no paid API is available.
    Results are basic but don't require authentication.
    """
    try:
        # DuckDuckGo instant answer API (free, no key required)
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        results = []
        
        # Add abstract if available
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data.get("Abstract", ""),
                "link": data.get("AbstractURL", ""),
                "source": "duckduckgo",
            })
        
        # Add related topics
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:100],
                    "snippet": topic.get("Text", ""),
                    "link": topic.get("FirstURL", ""),
                    "source": "duckduckgo",
                })
        
        logger.info(f"DuckDuckGo returned {len(results)} results for '{query[:50]}'")
        return results[:num_results]
        
    except Exception as e:
        logger.error(f"DuckDuckGo search error: {e}")
        return []


def fetch_wikipedia_summary(topic: str) -> Optional[Dict[str, Any]]:
    """
    Fetch Wikipedia summary for a topic (good for agricultural terms, crops, pests).
    
    No API key required. Good for factual agricultural information.
    """
    try:
        # Wikipedia API
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + topic.replace(" ", "_")
        
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get("type") == "standard":
            return {
                "title": data.get("title", ""),
                "summary": data.get("extract", ""),
                "link": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "source": "wikipedia",
            }
        
        return None
        
    except Exception as e:
        logger.debug(f"Wikipedia fetch failed for '{topic}': {e}")
        return None


def search_agricultural_databases(query: str, crop_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search agricultural-specific databases and resources.
    
    Sources:
    - USDA NASS (crop data)
    - FAO (global agriculture)
    - Agricultural extension databases
    - Crop pest/disease databases
    """
    results = []
    
    # Example: Search for crop-specific information
    if crop_type:
        wiki_result = fetch_wikipedia_summary(f"{crop_type} agriculture")
        if wiki_result:
            results.append(wiki_result)
    
    # Add more agricultural database integrations here
    # Example: USDA API, FAO API, university extension databases
    
    return results


def smart_search(query: str, location: Optional[str] = None, num_results: int = 3) -> Dict[str, Any]:
    """
    Intelligent search that tries multiple sources and returns best results.
    
    Priority:
    1. Try Google Custom Search (best quality, requires API key)
    2. Try SerpAPI (good quality, requires API key)
    3. Fall back to DuckDuckGo (free, basic results)
    4. Check Wikipedia for factual info
    
    Args:
        query: Search query
        location: Geographic location for search context
        num_results: Number of results to return
    
    Returns:
        Dict with search results and metadata
    """
    results = []
    search_method = "none"
    
    # Try Google Custom Search first (best quality)
    if GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID:
        results = search_google_custom(query, num_results)
        if results:
            search_method = "google_custom_search"
    
    # Try SerpAPI if Google didn't work
    if not results and SERPAPI_KEY:
        results = search_serpapi(query, num_results, location or "United States")
        if results:
            search_method = "serpapi"
    
    # Fall back to DuckDuckGo (free, no key required)
    if not results:
        results = search_duckduckgo(query, num_results)
        if results:
            search_method = "duckduckgo"
    
    # Try Wikipedia for factual information
    wiki_result = fetch_wikipedia_summary(query)
    if wiki_result and wiki_result not in results:
        results.append(wiki_result)
    
    return {
        "query": query,
        "results": results[:num_results],
        "search_method": search_method,
        "total_results": len(results),
        "has_results": len(results) > 0,
    }


def format_search_results_for_ai(search_data: Dict[str, Any]) -> str:
    """
    Format search results for AI consumption.
    
    Returns a concise summary of search results that can be added to AI context.
    """
    if not search_data.get("has_results"):
        return "No external search results available."
    
    lines = [f"External search results for '{search_data['query']}':"]
    
    for i, result in enumerate(search_data["results"], 1):
        title = result.get("title", "No title")
        snippet = result.get("snippet", "")[:200]  # Limit to 200 chars
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
    
    lines.append(f"\nSource: {search_data['search_method']}")
    
    return "\n".join(lines)


def should_search_externally(question: str) -> bool:
    """
    Determine if a question should trigger external search.
    
    Triggers for:
    - Questions about current events, prices, news
    - Questions with "latest", "current", "recent", "new"
    - Questions about specific diseases, pests not in knowledge base
    - Questions about locations, specific products
    """
    question_lower = question.lower()
    
    search_triggers = [
        "latest", "current", "recent", "new", "news",
        "price", "cost", "market",
        "what is", "who is", "when did", "where can",
        "how to", "best way",
        "disease", "pest", "infection",
    ]
    
    return any(trigger in question_lower for trigger in search_triggers)


def evaluate_internal_data_quality(backend_data: Dict[str, Any], question: str) -> Dict[str, Any]:
    """
    Evaluate if internal data is sufficient for answering the question.
    
    Returns:
        {
            "has_sufficient_internal_data": bool,
            "confidence": float (0-1),
            "internal_sources": list of available data sources,
            "gaps": list of missing information,
            "should_cross_reference": bool,
            "recommendation": str
        }
    """
    has_internal_sources = False
    internal_sources = []
    gaps = []
    confidence = 0.0
    
    question_lower = question.lower()
    
    # Check what internal data is available
    if backend_data.get("farm"):
        has_internal_sources = True
        internal_sources.append("farm_data")
        confidence += 0.2
    
    if backend_data.get("weather"):
        has_internal_sources = True
        internal_sources.append("weather_data")
        confidence += 0.15
    
    if backend_data.get("climate_report"):
        has_internal_sources = True
        internal_sources.append("climate_data")
        confidence += 0.15
    
    if backend_data.get("products_available"):
        has_internal_sources = True
        internal_sources.append("product_kb")
        confidence += 0.1
    
    if backend_data.get("stores_available"):
        has_internal_sources = True
        internal_sources.append("store_locations")
        confidence += 0.1
    
    # Identify information gaps
    if any(term in question_lower for term in ["latest", "current", "recent", "new", "news"]):
        gaps.append("Current/recent information (may need external source)")
        confidence -= 0.2
    
    if any(term in question_lower for term in ["price", "cost", "market"]):
        gaps.append("Current pricing/market data (needs external source)")
        confidence -= 0.15
    
    if any(term in question_lower for term in ["disease", "pest", "infection"]):
        target_data = None
        for source in internal_sources:
            if "product" in source or "farm" in source:
                target_data = "found"
        if not target_data:
            gaps.append("Specific disease/pest data (consider external reference)")
            confidence -= 0.1
    
    # Determine if cross-referencing is recommended
    should_cross_reference = (
        confidence < 0.5 or  # Low confidence in internal data alone
        len(gaps) > 0 or  # There are identified gaps
        any(term in question_lower for term in ["verify", "confirm", "check", "validate"])
    )
    
    # Generate recommendation
    if confidence >= 0.7 and not gaps:
        recommendation = "Use internal data only - high confidence"
    elif confidence >= 0.5 and not should_cross_reference:
        recommendation = "Internal data sufficient"
    else:
        recommendation = "Cross-reference with external sources for accuracy"
    
    return {
        "has_sufficient_internal_data": confidence >= 0.5 and not gaps,
        "confidence": max(0.0, min(1.0, confidence)),
        "internal_sources": internal_sources,
        "gaps": gaps,
        "should_cross_reference": should_cross_reference,
        "recommendation": recommendation,
    }


def combine_internal_and_external(internal_data: Dict[str, Any], external_search: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intelligently combine internal database data with external search results.
    
    Priority:
    1. Internal data for fact-based information (crops, farms, products)
    2. External data for current information (prices, latest treatments, news)
    3. Cross-reference to validate and enhance accuracy
    
    Returns:
        {
            "primary_source": "internal" | "external" | "combined",
            "internal_data": {...},
            "external_data": {...},
            "combined_insights": [...],
            "confidence": float,
            "source_attribution": str,
        }
    """
    # Determine which source is primary
    if not external_search.get("has_results"):
        return {
            "primary_source": "internal",
            "internal_data": internal_data,
            "external_data": None,
            "combined_insights": [],
            "confidence": 0.7,
            "source_attribution": "Internal knowledge base only (no external data available)",
            "recommendation": "Use internal data only - no external sources available",
        }
    
    if not any(internal_data.values()):
        return {
            "primary_source": "external",
            "internal_data": None,
            "external_data": external_search,
            "combined_insights": [],
            "confidence": 0.6,
            "source_attribution": "External sources (limited internal data)",
            "recommendation": "External sources provide the primary information",
        }
    
    # Both sources available - combine intelligently
    combined_insights = []
    confidence = 0.7
    
    # Extract key info from both sources
    internal_summary = _summarize_internal_data(internal_data)
    external_summary = _summarize_external_data(external_search)
    
    # Look for agreements and conflicts
    if internal_summary and external_summary:
        if _data_aligns(internal_summary, external_summary):
            combined_insights.append("✓ Internal data confirmed by external sources")
            confidence = 0.85
        else:
            combined_insights.append("⚠ Internal and external data differ - check both")
            confidence = 0.65
    
    return {
        "primary_source": "combined",
        "internal_data": internal_data,
        "external_data": external_search,
        "combined_insights": combined_insights,
        "confidence": confidence,
        "source_attribution": "Combined internal knowledge base and current external sources",
        "recommendation": "Answer grounded in internal data, validated by external sources",
    }


def _summarize_internal_data(internal_data: Dict[str, Any]) -> str:
    """Create brief summary of internal data for comparison"""
    summaries = []
    if internal_data.get("farm"):
        farm = internal_data["farm"]
        summaries.append(f"Farm: {farm.get('crop_type', 'Unknown')}")
    if internal_data.get("products_available"):
        summaries.append(f"Products: {len(internal_data['products_available'])} types available")
    return " | ".join(summaries) if summaries else ""


def _summarize_external_data(external_search: Dict[str, Any]) -> str:
    """Create brief summary of external search results"""
    if external_search.get("results"):
        titles = [r.get("title", "")[:50] for r in external_search["results"][:2]]
        return " | ".join(titles)
    return ""


def _data_aligns(internal: str, external: str) -> bool:
    """Check if internal and external data show similar concepts"""
    internal_words = set(internal.lower().split())
    external_words = set(external.lower().split())
    # If there's reasonable overlap in keywords, data aligns
    overlap = internal_words.intersection(external_words)
    return len(overlap) >= 2


def format_combined_response_for_ai(combined_data: Dict[str, Any], question: str) -> str:
    """
    Format combined internal and external data for AI consumption.
    
    Tells AI what sources are available and how confident we are in the data.
    """
    lines = [f"Data Analysis for: '{question}'"]
    lines.append(f"\nPrimary Source: {combined_data['primary_source'].upper()}")
    lines.append(f"Confidence Level: {combined_data['confidence']:.0%}")
    
    if combined_data.get("internal_data"):
        lines.append("\n📚 Internal Sources Available:")
        for source in combined_data.get("internal_sources", []):
            lines.append(f"  • {source}")
    
    if combined_data.get("external_data") and combined_data["external_data"].get("has_results"):
        lines.append("\n🌐 External Cross-Reference Available:")
        lines.append(f"  Method: {combined_data['external_data'].get('search_method')}")
        lines.append(f"  Results: {combined_data['external_data'].get('total_results')} sources found")
    
    if combined_data.get("combined_insights"):
        lines.append("\n✓ Analysis:")
        for insight in combined_data["combined_insights"]:
            lines.append(f"  {insight}")
    
    if combined_data.get("gaps"):
        lines.append("\n⚠ Information Gaps:")
        for gap in combined_data.get("gaps", []):
            lines.append(f"  • {gap}")
    
    lines.append(f"\nRecommendation: {combined_data.get('recommendation', 'Provide best answer from available sources')}")
    lines.append(f"Source Attribution: {combined_data.get('source_attribution', '')}")
    
    return "\n".join(lines)
