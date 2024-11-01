# Assuming `scraper.db` is an SQLite database, you can explore the data using Python and SQLite library.

import sqlite3
import webbrowser
import os

# Connect to the SQLite database
connection = sqlite3.connect('scraper.db')

# Create a cursor object
cursor = connection.cursor()

# Get the list of all tables in the database
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in the database:")
for table in tables:
    print(table[0])

# Select all data from a specific table (replace 'pages' with the actual table name you want to explore)
if tables:
    table_name = tables[0][0]  # Default to the first table in the list
    cursor.execute(f"SELECT * FROM {table_name} WHERE status != 'pending'")
    rows = cursor.fetchall()
    print(f"\nData from the table '{table_name}' (excluding pending status):")
    for row in rows:
        print(row)
        # If the status is 'scraped', print additional details about what was scraped
        if row[2] == 'scraped':
            html_file_path = f"scraped_data/{row[0].replace(':', '').replace('/', '_')}.html"
            print(f"Scraped content for URL {row[0]} on {row[1]}: (details here if available)")
            # Open the scraped HTML file if it exists
            if os.path.exists(html_file_path):
                print(f"Opening HTML file: {html_file_path}")
                webbrowser.open(f'file://{os.path.abspath(html_file_path)}')
            else:
                print(f"No HTML file found for {row[0]}")
else:
    print("No tables found in the database.")

# Close the connection
connection.close()
