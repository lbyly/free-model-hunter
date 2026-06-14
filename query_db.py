import sqlite3

conn = sqlite3.connect(r"d:\Free-Model-Hub\data\models.db")
cursor = conn.cursor()
cursor.execute("SELECT name, slug, scraper_class FROM providers")
print(cursor.fetchall())
conn.close()
