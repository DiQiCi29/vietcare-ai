import httpx
from bs4 import BeautifulSoup
import json

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
url = "https://vietro.com.vn/dieu-hoa-daikin"
r = httpx.get(url, headers=headers, timeout=15, verify=False)
soup = BeautifulSoup(r.text, "html.parser")

products = []
for h3 in soup.select("h3.p-tt"):
    a_tag = h3.find("a")
    if not a_tag:
        continue
    name = a_tag.text.strip()
    link = a_tag.get("href", "")
    
    # Find container
    parent = h3.find_parent("div")
    img_tag = parent.find("img") if parent else None
    img_url = img_tag.get("src", "") if img_tag else ""
    
    # Try to extract model (often in parentheses or at end of name)
    products.append({
        "name": name,
        "link": link,
        "image_url": img_url
    })

print(f"Scraped {len(products)} products from {url}")
for p in products[:5]:
    print("- Name:", p["name"])
    print("  Link:", p["link"])
    print("  Img:", p["image_url"])
