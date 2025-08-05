import sqlite3
conn = sqlite3.connect("idolapp.db")
c = conn.cursor()

c.execute("UPDATE match_posts SET likes=0 WHERE likes IS NULL;")
conn.commit()

conn.close()