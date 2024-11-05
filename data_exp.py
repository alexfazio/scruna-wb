import sqlite3
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

def is_content_page(url):
    """
    Determine if a URL is likely a content page rather than an asset.
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # List of asset patterns and extensions to filter out
    asset_patterns = ['/assets/', '/static/', '/dist/', '/js/', '/css/', '/images/']
    asset_extensions = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg']
    
    return not (
        any(pattern in path for pattern in asset_patterns) or
        any(path.endswith(ext) for ext in asset_extensions)
    )

def get_file_path(url):
    """Get the file path for a given URL."""
    filename = url.replace('/', '_').replace(':', '_').replace('?', '_').replace('&', '_')
    return Path('scraped_data') / f'{filename}.html'

def connect_db():
    """Connect to the SQLite database."""
    return sqlite3.connect('scraper.db')

def get_scraped_pages(db):
    """Get all successfully scraped HTML pages from the database."""
    cursor = db.cursor()
    cursor.execute('SELECT url, timestamp, status FROM pages WHERE status = "scraped"')
    return [page for page in cursor.fetchall() if is_content_page(page[0])]

def get_error_pages(db):
    """Get all pages that encountered errors during scraping."""
    cursor = db.cursor()
    cursor.execute('SELECT url, timestamp, status FROM pages WHERE status = "error"')
    return [page for page in cursor.fetchall() if is_content_page(page[0])]

def main():
    if not os.path.exists('scraper.db'):
        print("Error: scraper.db not found. Please run the scraper first.")
        return

    # Ensure scraped_data directory exists
    Path('scraped_data').mkdir(exist_ok=True)
    
    db = connect_db()
    
    while True:
        print("\nWeb Archive Explorer")
        print("-------------------")
        print("1. List all successfully scraped pages")
        print("2. List pages with errors")
        print("3. Open a specific HTML file")
        print("4. Show scraping statistics")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ")
        
        if choice == '1':
            scraped_pages = get_scraped_pages(db)
            print(f"\nSuccessfully scraped pages ({len(scraped_pages)}):")
            for i, (url, timestamp, status) in enumerate(scraped_pages, 1):
                file_path = get_file_path(url)
                exists = "✓" if file_path.exists() else "✗"
                print(f"{i}. [{exists}] {url} (archived: {timestamp})")
            
            if scraped_pages:
                view = input("\nEnter number to view page (or press Enter to return): ")
                if view.isdigit() and 1 <= int(view) <= len(scraped_pages):
                    url = scraped_pages[int(view)-1][0]
                    file_path = get_file_path(url)
                    if file_path.exists():
                        webbrowser.open(f'file://{file_path.absolute()}')
                    else:
                        print(f"Error: HTML file not found at {file_path}")
        
        elif choice == '2':
            error_pages = get_error_pages(db)
            print(f"\nPages with errors ({len(error_pages)}):")
            for url, timestamp, status in error_pages:
                print(f"- {url} (timestamp: {timestamp})")
        
        elif choice == '3':
            html_files = list(Path('scraped_data').glob('*.html'))
            print(f"\nAvailable HTML files ({len(html_files)}):")
            for i, file in enumerate(html_files, 1):
                print(f"{i}. {file.stem}")
            
            if html_files:
                view = input("\nEnter number to view file (or press Enter to return): ")
                if view.isdigit() and 1 <= int(view) <= len(html_files):
                    webbrowser.open(f'file://{html_files[int(view)-1].absolute()}')
        
        elif choice == '4':
            cursor = db.cursor()
            cursor.execute('SELECT COUNT(*) as total FROM pages')
            total = cursor.fetchone()[0]
            
            scraped_pages = len(get_scraped_pages(db))
            error_pages = len(get_error_pages(db))
            
            print("\nScraping Statistics")
            print("-------------------")
            print(f"Total Content URLs: {total}")
            print(f"Scraped Content Pages: {scraped_pages}")
            print(f"Error Content Pages: {error_pages}")
            if total > 0:
                print(f"Success Rate: {(scraped_pages/total*100):.1f}%")
        
        elif choice == '5':
            break
    
    db.close()
    print("\nGoodbye!")

if __name__ == '__main__':
    main()
