import sqlite3

def init_db():
    conn = sqlite3.connect('research_vault.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS research_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            authors TEXT,
            pub_year INTEGER,
            abstract TEXT,
            keywords TEXT,
            related_links TEXT,
            upload_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database aur Table kamyabi se ban gaye hain!")

if __name__ == "__main__":
    init_db()