from flask import Flask, render_template, request, redirect, session, flash, jsonify
from database import get_db, initialize_database
from functools import wraps
from datetime import date

app=Flask(__name__)
app.secret_key='change-this-secret-before-production'
initialize_database()

def login_required(fn):
 @wraps(fn)
 def wrapper(*args,**kwargs):
  if 'user_id' not in session:return redirect('/login')
  return fn(*args,**kwargs)
 return wrapper

def bid(): return session['business_id']

@app.route('/')
def home(): return redirect('/dashboard' if 'user_id' in session else '/login')

@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  db=get_db(); u=db.execute('SELECT * FROM users WHERE username=? AND password=?',(request.form['username'].strip(),request.form['password'])).fetchone(); db.close()
  if u:
   session.update(user_id=u['id'],business_id=u['business_id'],user_name=u['name']); return redirect('/dashboard')
  return render_template('login.html',error='Invalid username or password')
 return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/dashboard')
@login_required
def dashboard():
 db=get_db(); b=bid(); today=date.today().isoformat()
 sales=db.execute('SELECT COALESCE(SUM(total_amount),0) total FROM sales WHERE business_id=? AND DATE(created_at)=?',(b,today)).fetchone()['total']
 expenses=db.execute('SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE business_id=? AND DATE(created_at)=?',(b,today)).fetchone()['total']
 stock=db.execute('SELECT COALESCE(SUM(stock_quantity*buying_price),0) total FROM products WHERE business_id=?',(b,)).fetchone()['total']
 potential=db.execute('SELECT COALESCE(SUM(stock_quantity*selling_price),0) total FROM products WHERE business_id=?',(b,)).fetchone()['total']
 count=db.execute('SELECT COUNT(*) total FROM products WHERE business_id=?',(b,)).fetchone()['total']
 low=db.execute('SELECT * FROM products WHERE business_id=? AND stock_quantity<=reorder_level ORDER BY stock_quantity',(b,)).fetchall()
 recent=db.execute('SELECT * FROM sales WHERE business_id=? ORDER BY created_at DESC LIMIT 5',(b,)).fetchall(); db.close()
 return render_template('dashboard.html',sales=sales,expenses=expenses,stock_value=stock,potential_revenue=potential,product_count=count,low_stock=low,recent_sales=recent,profit=sales-expenses)

@app.route('/products')
@login_required
def products():
 db=get_db(); q=request.args.get('q','').strip(); cat=request.args.get('category','').strip(); sql='SELECT * FROM products WHERE business_id=?'; p=[bid()]
 if q: sql+=' AND (name LIKE ? OR category LIKE ?)'; p += [f'%{q}%',f'%{q}%']
 if cat: sql+=' AND category=?'; p.append(cat)
 sql+=' ORDER BY name'; products=db.execute(sql,p).fetchall(); cats=db.execute('SELECT DISTINCT category FROM products WHERE business_id=? AND category!="" ORDER BY category',(bid(),)).fetchall(); db.close()
 return render_template('products.html',products=products,categories=cats,q=q,selected_category=cat)

@app.route('/products/add',methods=['GET','POST'])
@login_required
def add_product():
 if request.method=='POST':
  db=get_db(); db.execute('INSERT INTO products(business_id,name,category,buying_price,selling_price,stock_quantity,reorder_level) VALUES(?,?,?,?,?,?,?)',(bid(),request.form['name'].strip(),request.form.get('category','').strip(),float(request.form.get('buying_price') or 0),float(request.form.get('selling_price') or 0),int(request.form.get('stock_quantity') or 0),int(request.form.get('reorder_level') or 5))); db.commit(); db.close(); flash('Product added.','success'); return redirect('/products')
 return render_template('product_form.html',product=None,title='Add Product')

@app.route('/products/edit/<int:product_id>',methods=['GET','POST'])
@login_required
def edit_product(product_id):
 db=get_db(); product=db.execute('SELECT * FROM products WHERE id=? AND business_id=?',(product_id,bid())).fetchone()
 if not product: db.close(); return 'Product not found',404
 if request.method=='POST':
  db.execute('UPDATE products SET name=?,category=?,buying_price=?,selling_price=?,stock_quantity=?,reorder_level=? WHERE id=? AND business_id=?',(request.form['name'].strip(),request.form.get('category','').strip(),float(request.form.get('buying_price') or 0),float(request.form.get('selling_price') or 0),int(request.form.get('stock_quantity') or 0),int(request.form.get('reorder_level') or 5),product_id,bid())); db.commit(); db.close(); flash('Product updated.','success'); return redirect('/products')
 db.close(); return render_template('product_form.html',product=product,title='Edit Product')

@app.post('/products/delete/<int:product_id>')
@login_required
def delete_product(product_id):
 db=get_db(); db.execute('DELETE FROM products WHERE id=? AND business_id=?',(product_id,bid())); db.commit(); db.close(); flash('Product deleted.','success'); return redirect('/products')

@app.route('/pos')
@login_required
def pos():
 db=get_db(); products=db.execute('SELECT * FROM products WHERE business_id=? AND stock_quantity>0 ORDER BY name',(bid(),)).fetchall(); db.close(); return render_template('pos.html',products=products)

@app.post('/pos/sale')
@login_required
def sale():
 items=request.form.getlist('product_id'); qtys=request.form.getlist('quantity')
 if not items: flash('Add at least one product.','error'); return redirect('/pos')
 db=get_db(); total=0; clean=[]
 try:
  for pid,qty in zip(items,qtys):
   q=int(qty); p=db.execute('SELECT * FROM products WHERE id=? AND business_id=?',(pid,bid())).fetchone()
   if not p or q<1 or q>p['stock_quantity']: raise ValueError(f'Invalid quantity for {p["name"] if p else "product"}.')
   total += p['selling_price']*q; clean.append((p,q))
  cur=db.execute('INSERT INTO sales(business_id,total_amount,payment_method) VALUES(?,?,?)',(bid(),total,request.form.get('payment_method','cash'))); sale_id=cur.lastrowid
  for p,q in clean:
   db.execute('INSERT INTO sale_items(sale_id,product_id,quantity,unit_price,buying_price) VALUES(?,?,?,?,?)',(sale_id,p['id'],q,p['selling_price'],p['buying_price']))
   db.execute('UPDATE products SET stock_quantity=stock_quantity-? WHERE id=?',(q,p['id']))
  db.commit(); flash(f'Sale #{sale_id} completed: KSh {total:,.2f}.','success')
 except Exception as e:
  db.rollback(); flash(str(e),'error')
 finally: db.close()
 return redirect('/pos')

@app.route('/customers')
@login_required
def customers():
 db=get_db(); rows=db.execute('SELECT * FROM customers WHERE business_id=? ORDER BY name',(bid(),)).fetchall(); db.close(); return render_template('simple_list.html',title='Customers',subtitle='Customer records',rows=rows,kind='customers',fields=[('name','Name'),('phone','Phone'),('balance','Balance')])

@app.post('/customers/add')
@login_required
def add_customer():
 db=get_db(); db.execute('INSERT INTO customers(business_id,name,phone,balance) VALUES(?,?,?,0)',(bid(),request.form['name'].strip(),request.form.get('phone','').strip())); db.commit(); db.close(); flash('Customer added.','success'); return redirect('/customers')

@app.route('/suppliers')
@login_required
def suppliers():
 db=get_db(); rows=db.execute('SELECT * FROM suppliers WHERE business_id=? ORDER BY name',(bid(),)).fetchall(); db.close(); return render_template('simple_list.html',title='Suppliers',subtitle='Supplier records',rows=rows,kind='suppliers',fields=[('name','Name'),('phone','Phone'),('balance','Balance')])

@app.post('/suppliers/add')
@login_required
def add_supplier():
 db=get_db(); db.execute('INSERT INTO suppliers(business_id,name,phone,balance) VALUES(?,?,?,0)',(bid(),request.form['name'].strip(),request.form.get('phone','').strip())); db.commit(); db.close(); flash('Supplier added.','success'); return redirect('/suppliers')

@app.route('/expenses')
@login_required
def expenses():
 db=get_db(); rows=db.execute('SELECT * FROM expenses WHERE business_id=? ORDER BY created_at DESC',(bid(),)).fetchall(); total=db.execute('SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE business_id=?',(bid(),)).fetchone()['total']; db.close(); return render_template('expenses.html',rows=rows,total=total)

@app.post('/expenses/add')
@login_required
def add_expense():
 db=get_db(); db.execute('INSERT INTO expenses(business_id,description,amount,category) VALUES(?,?,?,?)',(bid(),request.form['description'].strip(),float(request.form['amount']),request.form.get('category','').strip())); db.commit(); db.close(); flash('Expense recorded.','success'); return redirect('/expenses')

@app.route('/reports')
@login_required
def reports():
 db=get_db(); b=bid(); sales=db.execute('SELECT COUNT(*) count,COALESCE(SUM(total_amount),0) total FROM sales WHERE business_id=?',(b,)).fetchone(); expenses=db.execute('SELECT COUNT(*) count,COALESCE(SUM(amount),0) total FROM expenses WHERE business_id=?',(b,)).fetchone(); stock=db.execute('SELECT COUNT(*) products,COALESCE(SUM(stock_quantity*buying_price),0) value FROM products WHERE business_id=?',(b,)).fetchone(); db.close(); return render_template('reports.html',sales=sales,expenses=expenses,stock=stock)

if __name__=='__main__': app.run(host='0.0.0.0',port=5000,debug=True)
