# External Search & Database Integration Guide

This guide explains how to enable the AI to access external resources like Google search and other databases for more accurate answers.

## 🔍 What's Available

The system now supports:
- **Google Custom Search API** (best quality, paid)
- **SerpAPI** (simplified Google, 100 free searches/month)
- **DuckDuckGo** (free, no API key, basic results)
- **Wikipedia** (free, good for factual agricultural info)
- **Custom agricultural databases** (extensible)

## 🚀 Quick Start

### Option 1: Free Setup (DuckDuckGo + Wikipedia)

**No configuration needed!** The system automatically falls back to free sources:
- DuckDuckGo for general searches
- Wikipedia for factual agricultural information

### Option 2: Google Custom Search (Recommended)

**Setup Steps:**

1. **Create Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one

2. **Enable Custom Search API**
   - Go to [APIs & Services](https://console.cloud.google.com/apis/library)
   - Search for "Custom Search API"
   - Click "Enable"

3. **Create API Key**
   - Go to [Credentials](https://console.cloud.google.com/apis/credentials)
   - Click "Create Credentials" → "API Key"
   - Copy your API key

4. **Create Search Engine**
   - Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
   - Click "Add" to create new search engine
   - Choose "Search the entire web"
   - Copy your Search Engine ID (looks like: `0123456789abcdef:xyz`)

5. **Add to Environment**
   ```bash
   # Windows PowerShell
   $env:GOOGLE_SEARCH_API_KEY="your-api-key-here"
   $env:GOOGLE_SEARCH_ENGINE_ID="your-engine-id-here"
   
   # Or add to .env file:
   GOOGLE_SEARCH_API_KEY=your-api-key-here
   GOOGLE_SEARCH_ENGINE_ID=0123456789abcdef:xyz
   ```

6. **Restart Server**
   ```powershell
   Get-Process python | Stop-Process -Force
   & ".\.venv\Scripts\python.exe" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

### Option 3: SerpAPI (Easy Setup, Free Tier)

**Setup Steps:**

1. **Sign Up**
   - Go to [SerpAPI](https://serpapi.com/)
   - Create free account (100 searches/month)

2. **Get API Key**
   - Copy API key from dashboard

3. **Add to Environment**
   ```powershell
   $env:SERPAPI_KEY="your-serpapi-key"
   
   # Or add to .env file:
   SERPAPI_KEY=your-serpapi-key
   ```

4. **Restart Server**

## 🧪 Testing External Search

### Test 1: Question That Triggers Search

```powershell
# Test with a "latest" question (triggers external search)
$body = @{
    question="What is the latest treatment for tomato blight?"
    latitude=18.0179
    longitude=-76.8099
    session_id="test"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/ai/ask" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body `
    -UseBasicParsing `
    -TimeoutSec 15 | Select-Object -ExpandProperty Content | ConvertFrom-Json
```

### Test 2: Check Search Method Used

```powershell
# Response will include search information
$r.context_sources  # Should include "external_sources"
```

## 📊 Search Triggers

The AI automatically searches externally when questions contain:
- `latest`, `current`, `recent`, `new`, `news`
- `price`, `cost`, `market`
- `what is`, `who is`, `when did`, `where can`
- `how to`, `best way`
- `disease`, `pest`, `infection`

## 🔧 Advanced: Add Custom Databases

### Example: USDA Crop Database

Add to `web_search.py`:

```python
def search_usda_database(crop: str) -> Dict[str, Any]:
    """Search USDA NASS database for crop information"""
    try:
        url = "https://quickstats.nass.usda.gov/api/api_GET/"
        params = {
            "key": os.getenv("USDA_API_KEY"),
            "commodity_desc": crop,
            "year": 2024,
        }
        response = requests.get(url, params=params, timeout=5)
        # Process response...
        return data
    except Exception as e:
        logger.error(f"USDA search failed: {e}")
        return {}
```

### Example: Weather Database Integration

```python
def get_weather_forecast(latitude: float, longitude: float) -> Dict[str, Any]:
    """Get 7-day weather forecast"""
    url = f"https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,precipitation_sum",
        "forecast_days": 7,
    }
    response = requests.get(url, params=params, timeout=5)
    return response.json()
```

## 📈 Monitoring Search Usage

Check logs for search activity:
```powershell
# Server logs show:
# "Triggering external search for question: ..."
# "External search found X results via google_custom_search"
```

## 💡 Best Practices

1. **Use Google Custom Search for production** - Best quality results
2. **Use SerpAPI for testing** - Free tier is generous
3. **DuckDuckGo is good fallback** - No keys needed
4. **Wikipedia for definitions** - Excellent for agricultural terms

## 🛠️ Troubleshooting

### Search Not Working?

Check environment variables:
```powershell
$env:GOOGLE_SEARCH_API_KEY
$env:SERPAPI_KEY
```

### Still Using Fallback?

Check server logs:
```
"External search returned no results"
```

Means API key is not configured or invalid.

### Quota Exceeded?

- Google: Check [Quotas](https://console.cloud.google.com/apis/api/customsearch.googleapis.com/quotas)
- SerpAPI: Check dashboard for usage

## 🎯 Result Quality

| Method | Quality | Speed | Cost | Setup |
|--------|---------|-------|------|-------|
| Google Custom | ⭐⭐⭐⭐⭐ | Fast | Paid | Medium |
| SerpAPI | ⭐⭐⭐⭐ | Fast | Free tier | Easy |
| DuckDuckGo | ⭐⭐⭐ | Medium | Free | None |
| Wikipedia | ⭐⭐⭐⭐ | Fast | Free | None |

## 📚 Additional Resources

- [Google Custom Search Docs](https://developers.google.com/custom-search/v1/overview)
- [SerpAPI Documentation](https://serpapi.com/docs)
- [DuckDuckGo API](https://duckduckgo.com/api)
- [Wikipedia API](https://www.mediawiki.org/wiki/API:Main_page)

---

**Questions?** Check server logs or test with the provided PowerShell commands!
