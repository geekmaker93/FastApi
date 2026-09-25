import os
import sqlite3

p = r"crop_app.db"
print("exists", os.path.exists(p))
if not os.path.exists(p):
    raise SystemExit(0)

con = sqlite3.connect(p)
cur = con.cursor()
print(cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
try:
    rows = cur.execute("SELECT id, user_id, length(token), platform FROM user_device_tokens LIMIT 10").fetchall()
    print("token_metadata", rows)
except Exception as e:
    print("token_query_error", repr(e))
con.close()
