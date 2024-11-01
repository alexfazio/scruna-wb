import asyncio
import aiohttp
from playwright.async_api import async_playwright
import aiosqlite
import os
import json
import random
from datetime import datetime
from bs4 import BeautifulSoup
import markdown

# Setup
DOMAIN = 'forum.keyboardmaestro.com'
CDX_API = f'http://web.archive.org/cdx/search/cdx?url={DOMAIN}/*&output=json&collapse=urlkey&filter=statuscode:200'
OUTPUT_DIR = 'scraped_data'

def generate_dynamic_headers(url, timestamp):
    """Generate headers dynamically based on URL and timestamp."""
    chrome_version = "130.0.0.0"
    return {
        "sec-ch-ua-platform": '"Windows"',
        "Referer": f"https://web.archive.org/web/{timestamp}/https://{url}",
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36",
        "sec-ch-ua": f'"Chromium";v="{chrome_version.split(".")[0]}", "Google Chrome";v="{chrome_version.split(".")[0]}", "Not?A_Brand";v="99"',
        "DNT": "1",
        "sec-ch-ua-mobile": "?0"
    }

async def fetch_archived_urls():
    print("Fetching archived URLs from CDX API...")
    headers = generate_dynamic_headers(DOMAIN, datetime.now().strftime("%Y%m%d%H%M%S"))
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(CDX_API) as resp:
            data = await resp.json()
            print(f"Total URLs fetched: {len(data) - 1}")
            url_dict = {}
            for row in data[1:]:
                url = row[2]
                timestamp = row[1]
                if url not in url_dict or timestamp > url_dict[url]:
                    url_dict[url] = timestamp
            print(f"Total unique URLs after collapsing: {len(url_dict)}")
            return url_dict

async def init_db():
    db = await aiosqlite.connect('scraper.db')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            timestamp TEXT,
            status TEXT
        )
    ''')
    await db.commit()
    return db

async def save_content(url, content):
    filename = url.replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    html_path = os.path.join(OUTPUT_DIR, f'{filename}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved HTML content to {html_path}")

    soup = BeautifulSoup(content, 'html.parser')

    data = {
        'url': url,
        'title': soup.title.string.strip() if soup.title and soup.title.string else '',
        'description': soup.find('meta', attrs={'name': 'description'})['content'].strip() if soup.find('meta', attrs={'name': 'description'}) else ''
    }
    json_path = os.path.join(OUTPUT_DIR, f'{filename}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved JSON data to {json_path}")

    md_content = markdown.markdown(str(soup.body)) if soup.body else ''
    md_path = os.path.join(OUTPUT_DIR, f'{filename}.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Saved Markdown content to {md_path}")

async def scrape_page(page, db, url, timestamp):
    archive_url = f'https://web.archive.org/web/{timestamp}id_/{url}'
    print(f"Scraping URL: {archive_url}")

    # Set headers for each request dynamically this might issues
    # will review
    headers = generate_dynamic_headers(url, timestamp)
    await page.set_extra_http_headers(headers)

    try:
        await page.goto(archive_url, timeout=60000, wait_until='networkidle')
        content = await page.content()
        await save_content(url, content)
        await db.execute('UPDATE pages SET status = ? WHERE url = ?', ('scraped', url))
        await db.commit()
        print(f"Successfully scraped: {url}")
    except Exception as e:
        await db.execute('UPDATE pages SET status = ? WHERE url = ?', ('error', url))
        await db.commit()
        print(f"Error scraping {url}: {e}")

    # Random delay between 10 seconds and 2 minutes
    delay = random.uniform(10, 120)
    print(f"Waiting for {delay:.2f} seconds before next request...")
    await asyncio.sleep(delay)

async def main():
    url_dict = await fetch_archived_urls()
    db = await init_db()

    print("Inserting URLs into the database...")
    for url, timestamp in url_dict.items():
        await db.execute(
            'INSERT OR IGNORE INTO pages (url, timestamp, status) VALUES (?, ?, ?)',
            (url, timestamp, 'pending')
        )
    await db.commit()
    print("Database setup complete.")

    print("Fetching pending URLs from the database...")
    async with db.execute(
        'SELECT url, timestamp FROM pages WHERE status = ?', ('pending',)
    ) as cursor:
        pending_rows = await cursor.fetchall()
        pending_urls = [(row[0], row[1]) for row in pending_rows]

    if not pending_urls:
        print('No URLs to process.')
        await db.close()
        return

    print(f"Total pending URLs to process: {len(pending_urls)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for url, timestamp in pending_urls:
            await scrape_page(page, db, url, timestamp)

        await browser.close()
    await db.close()
    print("Scraping completed.")

if __name__ == '__main__':
    asyncio.run(main())