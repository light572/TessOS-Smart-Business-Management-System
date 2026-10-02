import sqlite3
DATABASE='tessos.db'
def get_db():
 c=sqlite3.connect(DATABASE); c.row_factory=sqlite3.Row; return c
def initialize_database():
 c=get_db(); c.executescript(open('schema.sql',encoding='utf-8').read()); b=c.execute('SELECT id FROM businesses LIMIT 1').fetchone()
 if not b:
  c.execute('INSERT INTO businesses(name) VALUES(?)',('Tess Mama Enterprise',)); bid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
  c.execute('INSERT INTO users(business_id,name,username,password,role) VALUES(?,?,?,?,?)',(bid,'John Apiri','john','1234','owner'))
  c.executemany('INSERT INTO products(business_id,name,category,buying_price,selling_price,stock_quantity,reorder_level) VALUES(?,?,?,?,?,?,?)',[(bid,'Sugar 1kg','Groceries',150,180,20,5),(bid,'Bread','Bakery',55,70,15,5),(bid,'Milk 500ml','Dairy',50,70,25,8),(bid,'Soda 500ml','Beverages',45,70,30,10)])
 c.commit(); c.close()
