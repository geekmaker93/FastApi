import requests
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from datetime import datetime
import re

class BBCWeatherService:
    """
    BBC Weather RSS Feed Parser
    Fetches and parses BBC Weather RSS feeds for specified locations
    """
    
    # BBC Weather RSS Feed URLs by location code
    # Find location codes at: https://www.bbc.co.uk/weather/
    BBC_WEATHER_RSS_BASE = "https://weather-broker-cdn.api.bbci.co.uk/en/forecast/rss/3day"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 10
    
    def get_weather_for_location(self, location_code: int) -> Optional[Dict]:
        """
        Fetch and parse BBC Weather RSS for a specific location
        
        Args:
            location_code: BBC Weather location code (e.g., 2618426 for Montego Bay, Jamaica)
        
        Returns:
            Dictionary with weather data or None if fetch fails
        """
        try:
            url = f"{self.BBC_WEATHER_RSS_BASE}/{location_code}"
            response = self.session.get(url)
            response.raise_for_status()
            
            return self._parse_rss(response.text, location_code)
        except Exception as e:
            raise ValueError(f"Failed to fetch BBC Weather for location {location_code}: {str(e)}")
    
    def _parse_rss(self, rss_content: str, location_code: int) -> Dict:
        """Parse BBC Weather RSS XML content"""
        try:
            root = ET.fromstring(rss_content)
            
            # Extract namespace
            ns = {'': 'http://www.bbc.co.uk/weather'}
            
            # Get channel info
            channel = root.find('channel')
            if channel is None:
                raise ValueError("Invalid RSS format: no channel found")
            
            location = channel.findtext('title', 'Unknown Location')
            link = channel.findtext('link', '')
            
            # Get current item (most recent forecast)
            items = channel.findall('item')
            if not items:
                raise ValueError("No weather items found in RSS feed")
            
            current_item = items[0]
            title = current_item.findtext('title', '')
            description = current_item.findtext('description', '')
            pub_date = current_item.findtext('pubDate', datetime.now().isoformat())
            
            # Parse the description for weather details
            weather_data = self._parse_weather_description(description, title)
            
            return {
                'location_code': location_code,
                'location': location,
                'link': link,
                'published': pub_date,
                'title': title,
                'description': description,
                'weather': weather_data,
                'timestamp': datetime.now().isoformat()
            }
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse RSS XML: {str(e)}")
    
    def _parse_weather_description(self, description: str, title: str) -> Dict:
        """
        Extract weather metrics from BBC Weather description
        BBC format: "Minimum Temperature: 22°C, Wind Direction: south-easterly, Wind Speed: 13mph, ..."
        """
        weather = {
            'condition': 'Unknown',
            'temperature_c': None,
            'feels_like_c': None,
            'humidity_percent': None,
            'wind_speed_mph': None,
            'wind_direction': None,
            'visibility_km': None,
            'pressure_mb': None,
            'uv_index': None
        }
        
        # Extract temperature from title (format: "18°C (64°F)")
        temp_match = re.search(r'(\d+)°C', title)
        if temp_match:
            weather['temperature_c'] = int(temp_match.group(1))
        
        # Parse description for weather data (BBC format: "label: value, label: value, ...")
        if description:
            # Extract temperature (Minimum/Maximum Temperature: 22°C format)
            temp_match = re.search(r'(?:Minimum|Maximum)?\s*Temperature:\s*(\d+)°C', description)
            if temp_match:
                weather['temperature_c'] = int(temp_match.group(1))
            
            # Extract feels like
            feels_match = re.search(r'Feels like:\s*(\d+)°C', description)
            if feels_match:
                weather['feels_like_c'] = int(feels_match.group(1))
            
            # Extract humidity (format: "Humidity: 65%")
            humidity_match = re.search(r'Humidity:\s*(\d+)%', description)
            if humidity_match:
                weather['humidity_percent'] = int(humidity_match.group(1))
            
            # Extract wind speed (format: "Wind Speed: 13mph")
            wind_match = re.search(r'Wind Speed:\s*(\d+)\s*mph', description)
            if wind_match:
                weather['wind_speed_mph'] = int(wind_match.group(1))
            
            # Extract wind direction (format: "Wind Direction: south-easterly")
            direction_match = re.search(r'Wind Direction:\s*([a-z-]+)', description, re.IGNORECASE)
            if direction_match:
                weather['wind_direction'] = direction_match.group(1).title()
            
            # Extract visibility (format: "Visibility: Very Good" or "Visibility: 10km")
            visibility_match = re.search(r'Visibility:\s*([\d.]+)\s*km', description)
            if visibility_match:
                weather['visibility_km'] = float(visibility_match.group(1))
            
            # Extract pressure (format: "Pressure: 1013mb")
            pressure_match = re.search(r'Pressure:\s*(\d+)\s*mb', description)
            if pressure_match:
                weather['pressure_mb'] = int(pressure_match.group(1))
            
            # Extract UV index
            uv_match = re.search(r'UV Risk:\s*(\d+)', description)
            if uv_match:
                weather['uv_index'] = int(uv_match.group(1))
            
            # Determine condition from description
            if 'sunny' in description.lower():
                weather['condition'] = 'Sunny'
            elif 'cloud' in description.lower():
                weather['condition'] = 'Cloudy'
            elif 'rain' in description.lower():
                weather['condition'] = 'Rainy'
            elif 'thunder' in description.lower():
                weather['condition'] = 'Thunderstorm'
            elif 'snow' in description.lower():
                weather['condition'] = 'Snowy'
            elif 'fog' in description.lower():
                weather['condition'] = 'Foggy'
            elif 'wind' in description.lower():
                weather['condition'] = 'Windy'
        
        return weather
    
    def get_forecast(self, location_code: int, hours: int = 24) -> Optional[List[Dict]]:
        """
        Fetch BBC Weather forecast for multiple hours ahead
        
        Args:
            location_code: BBC Weather location code
            hours: Number of hours ahead to forecast (default 24)
        
        Returns:
            List of hourly forecasts
        """
        try:
            url = f"{self.BBC_WEATHER_RSS_BASE}/{location_code}"
            response = self.session.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            channel = root.find('channel')
            
            items = channel.findall('item')[:hours]  # Limit to requested hours
            
            forecasts = []
            for item in items:
                title = item.findtext('title', '')
                description = item.findtext('description', '')
                pub_date = item.findtext('pubDate', '')
                
                weather_data = self._parse_weather_description(description, title)
                
                forecasts.append({
                    'time': pub_date,
                    'title': title,
                    'weather': weather_data
                })
            
            return forecasts
        except Exception as e:
            raise ValueError(f"Failed to fetch forecast: {str(e)}")


# Common BBC Weather location codes (add more as needed)
# To find codes: Visit https://www.bbc.co.uk/weather, search location, code is in URL
BBC_LOCATION_CODES = {
    'kingston_jamaica': 3489854,      # Kingston, Jamaica
    'montego_bay_jamaica': 3489460,   # Montego Bay, Jamaica  
    'london_uk': 2643743,              # London, UK
    'manchester_uk': 2643123,          # Manchester, UK
    'new_york_usa': 5128581,           # New York, USA
    'los_angeles_usa': 5368361,        # Los Angeles, USA
    'toronto_canada': 6167865,         # Toronto, Canada
    'mumbai_india': 1275339,           # Mumbai, India
    'sydney_australia': 2147714,       # Sydney, Australia
}


# Singleton instance
bbc_weather = BBCWeatherService()
