import asyncio, aiohttp, aiosqlite, os, json, random, datetime, markdown
from playwright.async_api import async_playwright
from datetime import datetime
from bs4 import BeautifulSoup

# Setup
DOMAIN = 'forum.keyboardmaestro.com'
CDX_API = f'http://web.archive.org/cdx/search/cdx?url={DOMAIN}/*&output=json&collapse=urlkey&filter=statuscode:200'
OUTPUT_DIR = 'scraped_data'


def generate_dynamic_headers(url: str, timestamp: str) -> dict:
    """
    Generate browser-like HTTP headers for web archive requests.

    Args:
        url (str): The target URL being requested
        timestamp (str): The wayback machine timestamp in format YYYYMMDDHHMMSS

    Returns:
        dict: A dictionary of HTTP headers including User-Agent, Referer, and security headers
    """
    chrome_version = "130.0.0.0"
    return {
        "sec-ch-ua-platform": '"Windows"',
        "Referer": (
            f"https://web.archive.org/web/{timestamp}/"
            f"https://{url}"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} "
            "Safari/537.36"
        ),
        "sec-ch-ua": (
            f'"Chromium";v="{chrome_version.split(".")[0]}", '
            f'"Google Chrome";v="{chrome_version.split(".")[0]}", '
            '"Not?A_Brand";v="99"'
        ),
        "DNT": "1",
        "sec-ch-ua-mobile": "?0"
    }


async def fetch_archived_urls() -> dict:
    """
    Fetch all archived URLs for the specified domain from the Wayback Machine CDX API.

    Returns:
        dict: A dictionary mapping URLs to their most recent timestamp
              {url: timestamp} where timestamp is in YYYYMMDDHHMMSS format

    Notes:
        - Uses the CDX API to get historical snapshots
        - Collapses multiple snapshots to keep only the most recent version of each URL
        - Prints progress information to stdout
    """
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


async def init_db() -> aiosqlite.Connection:
    """
    Initialize SQLite database connection and create required tables.

    Returns:
        aiosqlite.Connection: Database connection object

    Notes:
        Creates a 'pages' table with schema:
        - url (TEXT PRIMARY KEY)
        - timestamp (TEXT)
        - status (TEXT)
    """
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


async def save_content(url: str, content: str) -> None:
    """
    Save scraped content in multiple formats (HTML, JSON, Markdown).

    Args:
        url (str): The source URL of the content
        content (str): The raw HTML content to save

    Notes:
        Saves three files in the OUTPUT_DIR:
        - {filename}.html: Raw HTML content
        - {filename}.json: Metadata including title and description
        - {filename}.md: HTML converted to Markdown format
        
        Filenames are generated by replacing URL special characters with underscores
    """
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
        'description': soup.find('meta', attrs={'name': 'description'})['content'].strip() if soup.find('meta', attrs={
            'name': 'description'}) else ''
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


async def scrape_page(page, db: aiosqlite.Connection, url: str, timestamp: str) -> None:
    """
    Scrape a single page from the Wayback Machine archive.

    Args:
        page: Playwright page object
        db (aiosqlite.Connection): Database connection
        url (str): URL to scrape
        timestamp (str): Wayback Machine timestamp in YYYYMMDDHHMMSS format

    Notes:
        - Uses dynamic headers for each request
        - Implements random delays between requests (10-120 seconds)
        - Updates page status in database ('scraped' or 'error')
        - Handles timeouts and errors gracefully
    """
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


async def main() -> None:
    """
    Main execution function for the web scraper.

    Process:
    1. Fetches all archived URLs from Wayback Machine
    2. Initializes/updates the SQLite database
    3. Processes all pending URLs sequentially
    4. Saves content and updates status for each URL

    Notes:
        - Uses Playwright for browser automation
        - Maintains state in SQLite database
        - Handles one URL at a time to respect rate limits
        - Prints progress information throughout execution
    """
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
