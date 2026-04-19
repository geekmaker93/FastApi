import requests

r = requests.get('http://192.168.100.64:8000/news/?limit=2')
articles = r.json()['items']
for i, article in enumerate(articles, 1):
    print(f'Article {i}:')
    print(f'  Title: {article.get("title", "N/A")[:50]}')
    url = article.get('image_url', '')
    if url:
        print(f'  Image URL: {url}')
        print(f'  Has 640x360: {"640x360" in url}')
    else:
        print('  Image: None')
    print()
