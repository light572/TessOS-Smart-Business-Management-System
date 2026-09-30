import sqlite3

DATABASE = "tessos.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    conn = get_db()

    with open("schema.sql", "r", encoding="utf-8") as file:
        conn.executescript(file.read())

    business = conn.execute("SELECT id FROM businesses LIMIT 1").fetchone()

    if not business:
        conn.execute("""
            INSERT INTO businesses (name, phone, email, address)
            VALUES (?, ?, ?, ?)
        """, ("Tess Mama Enterprise", "", "", ""))

        business_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        conn.execute("""
            INSERT INTO users
            (business_id, name, username, password, role)
            VALUES (?, ?, ?, ?, ?)
        """, (business_id, "John Apiri", "john", "1234", "owner"))

        products = [
            ("Sugar 1kg", "Groceries", 150, 180, 20, 5),
            ("Bread", "Bakery", 55, 70, 15, 5),
            ("Milk 500ml", "Dairy", 50, 70, 25, 8),
            ("Soda 500ml", "Beverages", 45, 70, 30, 10)
        ]

        conn.executemany("""
            INSERT INTO products
            (business_id, name, category, buying_price, selling_price,
             stock_quantity, reorder_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [(business_id, *p) for p in products])

    conn.commit()
    conn.close()
