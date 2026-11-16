# DEMO ONLY: deliberately vulnerable code for the red-branch exercise. Never merge.
def search_products_insecure(cur, term):
    cur.execute(f"SELECT id, name FROM products WHERE name LIKE '%{term}%'")
    return cur.fetchall()
