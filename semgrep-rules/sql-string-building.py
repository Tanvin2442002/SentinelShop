def examples(cur, user_id, name):
    # ruleid: sentinelshop-sql-string-building
    cur.execute(f"SELECT * FROM products WHERE name = '{name}'")
    # ruleid: sentinelshop-sql-string-building
    cur.execute("SELECT * FROM products WHERE name = '%s'" % name)
    # ruleid: sentinelshop-sql-string-building
    cur.execute("SELECT * FROM products WHERE id = {}".format(user_id))
    # ruleid: sentinelshop-sql-string-building
    cur.execute("SELECT * FROM products WHERE name = '" + name + "'")
    # ok: sentinelshop-sql-string-building
    cur.execute("SELECT * FROM products WHERE name = %s", (name,))