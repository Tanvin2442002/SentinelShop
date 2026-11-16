# DEMO ONLY: fixed version of the red-branch exercise. The value is passed as a parameter.
def search_products(cur, term):
    cur.execute("SELECT id, name FROM products WHERE name LIKE %s", (f"%{term}%",))
    return cur.fetchall()
