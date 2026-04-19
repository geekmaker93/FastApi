import requests
import time

# Test speed
start = time.time()
r = requests.get('http://192.168.100.64:8000/news/all?limit=50&offset=0', timeout=30)
elapsed = time.time() - start

data = r.json()
print(f'First load: {elapsed:.2f}s')
print(f'Articles returned: {data["returned_articles"]}')
print(f'Total available: {data["total_articles"]}')
print()

# Test cache (should be much faster)
start = time.time()
r = requests.get('http://192.168.100.64:8000/news/all?limit=50&offset=50', timeout=30)
elapsed = time.time() - start

data = r.json()
print(f'Second load (cached): {elapsed:.2f}s')
print(f'Articles returned: {data["returned_articles"]}')
