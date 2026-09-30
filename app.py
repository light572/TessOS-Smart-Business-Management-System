from flask import Flask, render_template, request, redirect, session
from database import get_db, initialize_database
from functools import wraps
from datetime import date

app = Flask(__name__)
app.secret_key = "change-this-secret-before-production"

initialize_database()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    return redirect("/dashboard" if "user_id" in session else "/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        db.close()

        if user:
            session["user_id"] = user["id"]
            session["business_id"] = user["business_id"]
            session["user_name"] = user["name"]
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
@login_required
def dashboard():
    business_id = session["business_id"]
    today = date.today().isoformat()
    db = get_db()

    sales = db.execute("""
        SELECT COALESCE(SUM(total_amount), 0) AS total
        FROM sales
        WHERE business_id = ? AND DATE(created_at) = ?
    """, (business_id, today)).fetchone()["total"]

    expenses = db.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE business_id = ? AND DATE(created_at) = ?
    """, (business_id, today)).fetchone()["total"]

    stock_value = db.execute("""
        SELECT COALESCE(SUM(stock_quantity * buying_price), 0) AS total
        FROM products WHERE business_id = ?
    """, (business_id,)).fetchone()["total"]

    product_count = db.execute("""
        SELECT COUNT(*) AS total FROM products WHERE business_id = ?
    """, (business_id,)).fetchone()["total"]

    low_stock = db.execute("""
        SELECT * FROM products
        WHERE business_id = ? AND stock_quantity <= reorder_level
        ORDER BY stock_quantity ASC
    """, (business_id,)).fetchall()

    recent_sales = db.execute("""
        SELECT * FROM sales
        WHERE business_id = ?
        ORDER BY created_at DESC LIMIT 5
    """, (business_id,)).fetchall()

    db.close()

    # Foundation metric only. True gross profit will be calculated from sale_items in the POS phase.
    profit = sales - expenses

    return render_template(
        "dashboard.html",
        sales=sales,
        expenses=expenses,
        stock_value=stock_value,
        product_count=product_count,
        low_stock=low_stock,
        recent_sales=recent_sales,
        profit=profit
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
