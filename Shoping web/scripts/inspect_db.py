import sqlite3
DB = r"c:\Users\UCHENBA\Desktop\Shoping web\data.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
try:
    cols = cur.execute("PRAGMA table_info(users)").fetchall()
    print('COLUMNS:')
    for c in cols:
        print(c)
    cnt = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print('\nUSER COUNT:', cnt)
    rows = cur.execute("SELECT id,username,full_name,phone,created_at FROM users ORDER BY id DESC LIMIT 5").fetchall()
    print('\nSAMPLE ROWS:')
    for r in rows:
        print(r)
except Exception as e:
    print('ERROR:', e)
finally:
    conn.close()
