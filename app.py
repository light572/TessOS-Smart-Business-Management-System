from flask import Flask, render_template, request, redirect, session, flash
from database import get_db, initialize_database
from functools import wraps
from datetime import date

app = Flask(__name__)
app.secret_key = "change-this-secret-before-production"
initialize_database()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session: return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper

def bid(): return session["business_id"]

@app.route("/")
def home(): return redirect("/dashboard" if "user_id" in session else "/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db=get_db(); user=db.execute("SELECT * FROM users WHERE username=? AND password=?",(request.form["username"].strip(),request.form["password"])).fetchone(); db.close()
        if user:
            session.update(user_id=user["id"], business_id=user["business_id"], user_name=user["name"]); return redirect("/dashboard")
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

@app.route("/dashboard")
@login_required
def dashboard():
    db=get_db(); today=date.today().isoformat(); b=bid()
    sales=db.execute("SELECT COALESCE(SUM(total_amount),0) total FROM sales WHERE business_id=? AND DATE(created_at)=?",(b,today)).fetchone()["total"]
    expenses=db.execute("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE business_id=? AND DATE(created_at)=?",(b,today)).fetchone()["total"]
    stock=db.execute("SELECT COALESCE(SUM(stock_quantity*buying_price),0) total FROM products WHERE business_id=?",(b,)).fetchone()["total"]
    potential=db.execute("SELECT COALESCE(SUM(stock_quantity*selling_price),0) total FROM products WHERE business_id=?",(b,)).fetchone()["total"]
    count=db.execute("SELECT COUNT(*) total FROM products WHERE business_id=?",(b,)).fetchone()["total"]
    low=db.execute("SELECT * FROM products WHERE business_id=? AND stock_quantity<=reorder_level ORDER BY stock_quantity",(b,)).fetchall()
    recent=db.execute("SELECT * FROM sales WHERE business_id=? ORDER BY created_at DESC LIMIT 5",(b,)).fetchall(); db.close()
    return render_template("dashboard.html",sales=sales,expenses=expenses,stock_value=stock,potential_revenue=potential,product_count=count,low_stock=low,recent_sales=recent,profit=sales-expenses)

@app.route("/products")
@login_required
def products():
    db=get_db(); q=request.args.get("q","").strip(); cat=request.args.get("category","").strip(); sql="SELECT * FROM products WHERE business_id=?"; params=[bid()]
    if q: sql+=" AND (name LIKE ? OR category LIKE ?)"; params += [f"%{q}%",f"%{q}%"]
    if cat: sql+=" AND category=?"; params.append(cat)
    sql+=" ORDER BY name"; products=db.execute(sql,params).fetchall(); cats=db.execute("SELECT DISTINCT category FROM products WHERE business_id=? AND category!='' ORDER BY category",(bid(),)).fetchall(); db.close()
    return render_template("products.html",products=products,categories=cats,q=q,selected_category=cat)

@app.route("/products/add", methods=["GET","POST"])
@login_required
def add_product():
    if request.method=="POST":
        name=request.form["name"].strip(); category=request.form.get("category","").strip(); buy=float(request.form.get("buying_price") or 0); sell=float(request.form.get("selling_price") or 0); stock=int(request.form.get("stock_quantity") or 0); reorder=int(request.form.get("reorder_level") or 5)
        if not name: flash("Product name is required.","error"); return redirect("/products/add")
        db=get_db(); db.execute("INSERT INTO products (business_id,name,category,buying_price,selling_price,stock_quantity,reorder_level) VALUES (?,?,?,?,?,?,?)",(bid(),name,category,buy,sell,stock,reorder)); db.commit(); db.close(); flash(f"{name} was added successfully.","success"); return redirect("/products")
    return render_template("product_form.html",product=None,title="Add Product")

@app.route("/products/edit/<int:product_id>", methods=["GET","POST"])
@login_required
def edit_product(product_id):
    db=get_db(); product=db.execute("SELECT * FROM products WHERE id=? AND business_id=?",(product_id,bid())).fetchone()
    if not product: db.close(); return "Product not found",404
    if request.method=="POST":
        name=request.form["name"].strip(); category=request.form.get("category","").strip(); buy=float(request.form.get("buying_price") or 0); sell=float(request.form.get("selling_price") or 0); stock=int(request.form.get("stock_quantity") or 0); reorder=int(request.form.get("reorder_level") or 5)
        db.execute("UPDATE products SET name=?,category=?,buying_price=?,selling_price=?,stock_quantity=?,reorder_level=? WHERE id=? AND business_id=?",(name,category,buy,sell,stock,reorder,product_id,bid())); db.commit(); db.close(); flash(f"{name} was updated.","success"); return redirect("/products")
    db.close(); return render_template("product_form.html",product=product,title="Edit Product")

@app.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    db=get_db(); p=db.execute("SELECT name FROM products WHERE id=? AND business_id=?",(product_id,bid())).fetchone()
    if p: db.execute("DELETE FROM products WHERE id=? AND business_id=?",(product_id,bid())); db.commit(); flash(f"{p['name']} was deleted.","success")
    db.close(); return redirect("/products")

if __name__ == "__main__": app.run(host="0.0.0.0",port=5000,debug=True)
