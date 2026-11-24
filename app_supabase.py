
import os
import logging
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from functools import wraps
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash,
    abort
)
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from database_supabase import get_db


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

secret_key = os.getenv("SECRET_KEY")

if not secret_key:
    raise RuntimeError(
        "SECRET_KEY is missing. Check your project's .env file."
    )

app.config["SECRET_KEY"] = secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)

app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8

logging.basicConfig(level=logging.INFO)


# ============================================================
# GENERAL HELPERS
# ============================================================

NAIROBI = ZoneInfo("Africa/Nairobi")


def bid():
    """Return the authenticated user's business ID."""
    business_id = session.get("business_id")

    if not business_id:
        abort(403)

    return business_id


def current_user():
    """Return basic authenticated user information."""
    return {
        "id": session.get("user_id"),
        "business_id": session.get("business_id"),
        "name": session.get("user_name"),
        "role": session.get("role")
    }


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")

        return function(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(function):

        @wraps(function)
        @login_required
        def wrapper(*args, **kwargs):

            if session.get("role") not in allowed_roles:
                flash(
                    "You do not have permission to perform that action.",
                    "error"
                )
                return redirect("/dashboard")

            return function(*args, **kwargs)

        return wrapper

    return decorator
# ============================================================
# CUSTOMER AUTHENTICATION
# ============================================================

def customer_login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if (
            not session.get("customer_account_id")
            or session.get("role") != "customer"
        ):
            return redirect("/customer/login")

        return function(*args, **kwargs)

    return wrapper


def whole_number(value):
    """Validate an integer quantity."""
    try:
        number = Decimal(str(value).strip())

        if not number.is_finite():
            raise ValueError

        if number != number.to_integral_value():
            raise ValueError

        return int(number)

    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("Enter a valid whole number.")


def money_number(value, field_name="Amount"):
    """Validate a non-negative monetary amount."""
    try:
        number = Decimal(str(value).strip())

        if not number.is_finite() or number < 0:
            raise ValueError

        return number

    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f"Enter a valid {field_name.lower()}.")


def get_today():
    """Get today's date using Kenya's local timezone."""
    return datetime.now(NAIROBI).date()


def safe_uuid(value):
    """Convert a submitted ID into a UUID."""
    try:
        return UUID(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid record ID.")


def business_user():
    """Check whether a user belongs to the current business."""
    if "user_id" not in session or "business_id" not in session:
        abort(403)

    return session["business_id"]


# ============================================================
# HOME AND AUTHENTICATION
# ============================================================

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")

    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template(
                "login.html",
                error="Enter your username and password."
            )

        try:
            with get_db() as db:

                users = db.execute(
                    """
                    SELECT
                        id,
                        business_id,
                        name,
                        username,
                        password_hash,
                        role
                    FROM users
                    WHERE username = %s
                    """,
                    (username,)
                ).fetchall()

            authenticated_user = None

            for user in users:

                stored_hash = user["password_hash"]

                if stored_hash and check_password_hash(
                    stored_hash,
                    password
                ):
                    authenticated_user = user
                    break

            if authenticated_user:

                session.clear()

                session["user_id"] = str(authenticated_user["id"])
                session["business_id"] = str(
                    authenticated_user["business_id"]
                )
                session["user_name"] = authenticated_user["name"]
                session["role"] = authenticated_user["role"]
                session.permanent = True

                flash("Welcome back!", "success")

                return redirect("/dashboard")

            return render_template(
                "login.html",
                error="Invalid username or password."
            )

        except Exception:
            app.logger.exception("Login error")

            return render_template(
                "login.html",
                error="Login is temporarily unavailable. Try again."
            )

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect("/login")
# ============================================================
# CUSTOMER REGISTRATION
# ============================================================

@app.route("/customer/register", methods=["GET", "POST"])
def customer_register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, phone, email, password, confirm_password]):
            return render_template(
                "customer_register.html",
                error="Please fill in all fields."
            )

        if len(password) < 8:
            return render_template(
                "customer_register.html",
                error="Password must be at least 8 characters."
            )

        if password != confirm_password:
            return render_template(
                "customer_register.html",
                error="Passwords do not match."
            )

        try:
            with get_db() as db:

                business = db.execute(
                    """
                    SELECT id FROM businesses
                    WHERE name = %s
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    ("Tess Mama Enterprise",)
                ).fetchone()

                if not business:
                    return render_template(
                        "customer_register.html",
                        error="Business account not found."
                    )

                business_id = business["id"]

                existing = db.execute(
                    """
                    SELECT id FROM customer_accounts
                    WHERE business_id = %s
                    AND LOWER(email) = %s
                    """,
                    (business_id, email)
                ).fetchone()

                if existing:
                    return render_template(
                        "customer_register.html",
                        error="This email is already registered."
                    )

                customer = db.execute(
                    """
                    INSERT INTO customers (
                        business_id,
                        name,
                        phone
                    )
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (business_id, name, phone)
                ).fetchone()

                db.execute(
                    """
                    INSERT INTO customer_accounts (
                        business_id,
                        customer_id,
                        email,
                        password_hash
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        business_id,
                        customer["id"],
                        email,
                        generate_password_hash(password)
                    )
                )

            flash(
                "Account created successfully. Please sign in.",
                "success"
            )

            return redirect("/customer/login")

        except Exception:
            app.logger.exception("Customer registration error")

            return render_template(
                "customer_register.html",
                error="Registration failed. Please try again."
            )

    return render_template("customer_register.html")
# ============================================================
# CUSTOMER LOGIN
# ============================================================

@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template(
                "customer_login.html",
                error="Enter your email and password."
            )

        try:
            with get_db() as db:
                account = db.execute(
                    """
                    SELECT
                        ca.id AS account_id,
                        ca.customer_id,
                        ca.business_id,
                        ca.password_hash,
                        c.name
                    FROM customer_accounts ca
                    JOIN customers c ON c.id = ca.customer_id
                    JOIN businesses b ON b.id = ca.business_id
                    WHERE LOWER(ca.email) = %s
                    AND b.name = %s
                    LIMIT 1
                    """,
                    (email, "Tess Mama Enterprise")
                ).fetchone()

            if account and check_password_hash(
                account["password_hash"], password
            ):
                session.clear()
                session["customer_account_id"] = str(account["account_id"])
                session["customer_id"] = str(account["customer_id"])
                session["business_id"] = str(account["business_id"])
                session["user_name"] = account["name"]
                session["role"] = "customer"
                session.permanent = True

                return redirect("/customer/dashboard")

            return render_template(
                "customer_login.html",
                error="Invalid email or password."
            )

        except Exception:
            app.logger.exception("Customer login error")
            return render_template(
                "customer_login.html",
                error="Login is temporarily unavailable. Please try again."
            )

    return render_template("customer_login.html")
# ============================================================
# CUSTOMER DASHBOARD
# ============================================================

@app.route("/customer/dashboard")
@customer_login_required
def customer_dashboard():

    return render_template(
        "customer_dashboard.html",
        customer_name=session.get("user_name", "Customer")
    )
# ============================================================
# CUSTOMER LOGOUT
# ============================================================

@app.route("/customer/logout")
@customer_login_required
def customer_logout():

    session.clear()

    flash("You have been logged out successfully.", "success")

    return redirect("/customer/login")
# ============================================================
# CUSTOMER PROFILE
# ============================================================

@app.route("/customer/profile", methods=["GET", "POST"])
@customer_login_required
def customer_profile():

    business_id = session.get("business_id")
    customer_id = session.get("customer_id")

    try:
        with get_db() as db:

            customer = db.execute(
                """
                SELECT id, name, phone
                FROM customers
                WHERE id = %s
                  AND business_id = %s
                """,
                (customer_id, business_id)
            ).fetchone()

            if not customer:
                flash("Customer profile not found.", "error")
                return redirect("/customer/dashboard")

            if request.method == "POST":

                name = request.form.get("name", "").strip()
                phone = request.form.get("phone", "").strip()

                if not name or not phone:
                    return render_template(
                        "customer_profile.html",
                        customer={
                            "name": name,
                            "phone": phone
                        },
                        error="Please complete all fields."
                    )

                if len(name) > 150 or len(phone) > 30:
                    return render_template(
                        "customer_profile.html",
                        customer={
                            "name": name,
                            "phone": phone
                        },
                        error="Please check the length of your details."
                    )

                db.execute(
                    """
                    UPDATE customers
                    SET name = %s,
                        phone = %s
                    WHERE id = %s
                      AND business_id = %s
                    """,
                    (name, phone, customer_id, business_id)
                )

                session["user_name"] = name
                session.modified = True

                flash("Profile updated successfully.", "success")
                return redirect("/customer/profile")

        return render_template(
            "customer_profile.html",
            customer=customer,
            error=None
        )

    except Exception:
        app.logger.exception("Customer profile error")
        flash("Could not update your profile.", "error")
        return redirect("/customer/dashboard")
# ============================================================
# CUSTOMER PRODUCT CATALOGUE
# ============================================================

@app.route("/staff/orders/<uuid:order_id>")
@role_required("owner", "manager", "cashier")
def staff_order_detail(order_id):

    try:
        with get_db() as db:

            order = db.execute(
                """
                SELECT
                    o.id,
                    c.name AS customer_name,
                    o.phone,
                    o.delivery_address,
                    o.total_amount,
                    o.payment_status,
                    o.status,
                    o.created_at
                FROM online_orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.id = %s
                  AND o.business_id = %s
                """,
                (order_id, bid())
            ).fetchone()

            if not order:
                flash("Order not found.", "error")
                return redirect("/staff/orders")

            items = db.execute(
                """
                SELECT
                    product_name,
                    quantity,
                    unit_price
                FROM online_order_items
                WHERE order_id = %s
                """,
                (order_id,)
            ).fetchall()

        return render_template(
            "staff_order_detail.html",
            order=order,
            items=items
        )

    except Exception:
        app.logger.exception("Staff order detail error")
        flash("Could not load order details.", "error")
        return redirect("/staff/orders")
@app.route("/customer/products")
@customer_login_required
def customer_products():

    business_id = session.get("business_id")

    try:
        with get_db() as db:
            products = db.execute(
                """
                SELECT
                    id,
                    name,
                    category,
                    selling_price,
                    stock_quantity
                FROM products
                WHERE business_id = %s
                ORDER BY name ASC
                """,
                (business_id,)
            ).fetchall()

        return render_template(
            "customer_products.html",
            products=products
        )

    except Exception:
        app.logger.exception("Customer products loading error")
        flash("Could not load products. Please try again.", "error")
        return redirect("/customer/dashboard")
# ============================================================
# CUSTOMER SHOPPING CART
# ============================================================

@app.route(
    "/staff/orders/<uuid:order_id>/payment",
    methods=["POST"]
)
@role_required("owner", "manager", "cashier")
def staff_confirm_order_payment(order_id):

    payment_method = request.form.get(
        "payment_method", ""
    ).strip().lower()

    allowed_methods = {"cash", "mpesa"}

    if payment_method not in allowed_methods:
        flash("Invalid payment method.", "error")
        return redirect("/staff/orders")

    try:
        with get_db() as db:

            result = db.execute(
                """
                UPDATE online_orders
                SET payment_status = 'paid',
                    payment_method = %s,
                    updated_at = NOW()
                WHERE id = %s
                  AND business_id = %s
                  AND payment_status = 'unpaid'
                RETURNING id
                """,
                (payment_method, order_id, bid())
            ).fetchone()

        if result:
            flash(
                "Payment recorded successfully.",
                "success"
            )
        else:
            flash(
                "Order not found or payment already recorded.",
                "error"
            )

    except Exception:
        app.logger.exception("Payment confirmation error")
        flash("Could not record payment.", "error")

    return redirect("/staff/orders")
@app.route("/customer/cart")
@customer_login_required
def customer_cart():

    business_id = session.get("business_id")
    cart = session.get("customer_cart", {})

    cart_items = []
    total = Decimal("0")

    try:
        if cart:
            with get_db() as db:
                products = db.execute(
                    """
                    SELECT id, name, selling_price, stock_quantity
                    FROM products
                    WHERE business_id = %s
                      AND id::text = ANY(%s)
                    ORDER BY name
                    """,
                    (business_id, list(cart.keys()))
                ).fetchall()

            for product in products:
                quantity = int(cart[str(product["id"])])

                item_total = (
                    Decimal(str(product["selling_price"])) * quantity
                )

                cart_items.append({
                    "id": str(product["id"]),
                    "name": product["name"],
                    "selling_price": product["selling_price"],
                    "stock_quantity": product["stock_quantity"],
                    "quantity": quantity
                })

                total += item_total

        return render_template(
            "customer_cart.html",
            cart_items=cart_items,
            total=total
        )

    except Exception:
        app.logger.exception("Customer cart loading error")
        flash("Could not load your cart.", "error")
        return redirect("/customer/products")


@app.route("/customer/cart/add/<uuid:product_id>", methods=["POST"])
@customer_login_required
def customer_cart_add(product_id):

    try:
        quantity = int(request.form.get("quantity", "1"))

        if quantity < 1:
            raise ValueError()

        with get_db() as db:
            product = db.execute(
                """
                SELECT id, stock_quantity
                FROM products
                WHERE id = %s AND business_id = %s
                """,
                (product_id, session["business_id"])
            ).fetchone()

        if not product:
            flash("Product not found.", "error")
            return redirect("/customer/products")

        cart = session.get("customer_cart", {})
        key = str(product_id)

        new_quantity = int(cart.get(key, 0)) + quantity

        if new_quantity > product["stock_quantity"]:
            flash("Requested quantity exceeds available stock.", "error")
            return redirect("/customer/products")

        cart[key] = new_quantity
        session["customer_cart"] = cart
        session.modified = True

        flash("Product added to your cart.", "success")

    except ValueError:
        flash("Please enter a valid quantity.", "error")

    except Exception:
        app.logger.exception("Add to cart error")
        flash("Could not add product to cart.", "error")

    return redirect("/customer/products")


@app.route("/customer/cart/update/<uuid:product_id>", methods=["POST"])
@customer_login_required
def customer_cart_update(product_id):

    try:
        quantity = int(request.form.get("quantity", "0"))

        if quantity < 1:
            raise ValueError()

        with get_db() as db:
            product = db.execute(
                """
                SELECT stock_quantity
                FROM products
                WHERE id = %s AND business_id = %s
                """,
                (product_id, session["business_id"])
            ).fetchone()

        if not product:
            flash("Product is no longer available.", "error")
            return redirect("/customer/cart")

        if quantity > product["stock_quantity"]:
            flash("Requested quantity exceeds available stock.", "error")
            return redirect("/customer/cart")

        cart = session.get("customer_cart", {})
        key = str(product_id)

        if key not in cart:
            flash("Product is not in your cart.", "error")
            return redirect("/customer/cart")

        cart[key] = quantity
        session["customer_cart"] = cart
        session.modified = True

        flash("Cart updated successfully.", "success")

    except ValueError:
        flash("Please enter a valid quantity.", "error")

    except Exception:
        app.logger.exception("Cart update error")
        flash("Could not update your cart.", "error")

    return redirect("/customer/cart")


@app.route("/customer/cart/remove/<uuid:product_id>", methods=["POST"])
@customer_login_required
def customer_cart_remove(product_id):

    cart = session.get("customer_cart", {})
    cart.pop(str(product_id), None)

    session["customer_cart"] = cart
    session.modified = True

    flash("Product removed from your cart.", "success")

    return redirect("/customer/cart")
# ============================================================
# CUSTOMER CHECKOUT
# ============================================================

@app.route("/customer/checkout", methods=["GET", "POST"])
@customer_login_required
def customer_checkout():

    business_id = session.get("business_id")
    customer_id = session.get("customer_id")
    cart = session.get("customer_cart", {})

    if not cart:
        flash("Your shopping cart is empty.", "error")
        return redirect("/customer/products")

    try:
        with get_db() as db:

            customer = db.execute(
                """
                SELECT name, phone
                FROM customers
                WHERE id = %s AND business_id = %s
                """,
                (customer_id, business_id)
            ).fetchone()

            if not customer:
                abort(403)

            products = db.execute(
                """
                SELECT id, name, selling_price, stock_quantity
                FROM products
                WHERE business_id = %s
                  AND id::text = ANY(%s)
                """,
                (business_id, list(cart.keys()))
            ).fetchall()

            product_map = {
                str(product["id"]): product
                for product in products
            }

            if len(product_map) != len(cart):
                flash("Some products are no longer available.", "error")
                return redirect("/customer/cart")

            cart_items = []
            total = Decimal("0")

            for product_id, quantity_value in cart.items():

                product = product_map[product_id]
                quantity = int(quantity_value)
                stock = Decimal(str(product["stock_quantity"]))

                if quantity < 1 or Decimal(quantity) > stock:
                    flash(
                        "A requested quantity is no longer available.",
                        "error"
                    )
                    return redirect("/customer/cart")

                price = Decimal(str(product["selling_price"]))
                item_total = price * quantity
                total += item_total

                cart_items.append({
                    "id": product_id,
                    "name": product["name"],
                    "selling_price": price,
                    "quantity": quantity
                })

            if request.method == "GET":
                return render_template(
                    "customer_checkout.html",
                    cart_items=cart_items,
                    total=total,
                    customer_phone=customer["phone"] or "",
                    error=None
                )

            phone = request.form.get("phone", "").strip()
            delivery_address = request.form.get(
                "delivery_address", ""
            ).strip()

            if not phone or not delivery_address:
                return render_template(
                    "customer_checkout.html",
                    cart_items=cart_items,
                    total=total,
                    customer_phone=phone,
                    error="Enter your phone number and delivery details."
                )

            if len(phone) > 30 or len(delivery_address) > 500:
                return render_template(
                    "customer_checkout.html",
                    cart_items=cart_items,
                    total=total,
                    customer_phone=phone,
                    error="Please check the length of your details."
                )

            order = db.execute(
                """
                INSERT INTO online_orders (
                    business_id,
                    customer_id,
                    phone,
                    delivery_address,
                    total_amount
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    business_id,
                    customer_id,
                    phone,
                    delivery_address,
                    total
                )
            ).fetchone()

            for item in cart_items:
                db.execute(
                    """
                    INSERT INTO online_order_items (
                        order_id,
                        product_id,
                        product_name,
                        quantity,
                        unit_price
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        order["id"],
                        item["id"],
                        item["name"],
                        item["quantity"],
                        item["selling_price"]
                    )
                )

        session["customer_cart"] = {}
        session.modified = True

        flash("Your order has been submitted successfully.", "success")
        return redirect("/customer/orders")

    except Exception:
        app.logger.exception("Customer checkout error")
        flash("Checkout could not be completed. Please try again.", "error")
        return redirect("/customer/cart")
# ============================================================
# CUSTOMER ORDER HISTORY
# ============================================================

@app.route("/customer/orders")
@customer_login_required
def customer_orders():

    try:
        with get_db() as db:
            orders = db.execute(
                """
                SELECT
                    id,
                    total_amount,
                    status,
                    payment_status,
                    created_at
                FROM online_orders
                WHERE business_id = %s
                  AND customer_id = %s
                ORDER BY created_at DESC
                """,
                (
                    session["business_id"],
                    session["customer_id"]
                )
            ).fetchall()

        return render_template(
            "customer_orders.html",
            orders=orders
        )

    except Exception:
        app.logger.exception("Customer order history error")
        flash("Could not load your orders.", "error")
        return redirect("/customer/dashboard")
@app.route("/customer/orders/<uuid:order_id>")
@customer_login_required
def customer_order_detail(order_id):

    try:
        with get_db() as db:
            order = db.execute(
                """
                SELECT
                    id,
                    total_amount,
                    status,
                    payment_status,
                    phone,
                    delivery_address,
                    created_at
                FROM online_orders
                WHERE id = %s
                  AND business_id = %s
                  AND customer_id = %s
                """,
                (
                    order_id,
                    session["business_id"],
                    session["customer_id"]
                )
            ).fetchone()

            if not order:
                flash("Order not found.", "error")
                return redirect("/customer/orders")

            items = db.execute(
                """
                SELECT
                    product_name,
                    quantity,
                    unit_price,
                    quantity * unit_price AS item_total
                FROM online_order_items
                WHERE order_id = %s
                ORDER BY product_name
                """,
                (order_id,)
            ).fetchall()

        return render_template(
            "customer_order_detail.html",
            order=order,
            items=items
        )

    except Exception:
        app.logger.exception("Customer order detail error")
        flash("Could not load order details.", "error")
        return redirect("/customer/orders")

# ============================================================
# STAFF CUSTOMER ORDER MANAGEMENT
# ============================================================

@app.route("/staff/orders")
@role_required("owner", "manager", "cashier")
def staff_orders():

    try:
        with get_db() as db:
            orders = db.execute(
                """
                SELECT
                    o.id,
                    c.name AS customer_name,
                    o.phone,
                    o.total_amount,
                    o.payment_status,
                    o.payment_method,
                    o.status,
                    o.created_at
                FROM online_orders o
                LEFT JOIN customers c
                    ON c.id = o.customer_id
                WHERE o.business_id = %s
                ORDER BY o.created_at DESC
                """,
                (bid(),)
            ).fetchall()

        return render_template(
            "staff_orders.html",
            orders=orders
        )

    except Exception:
        app.logger.exception("Staff orders error")
        flash("Could not load customer orders.", "error")
        return redirect("/dashboard")


@app.route(
    "/staff/orders/<uuid:order_id>/status",
    methods=["POST"]
)
@role_required("owner", "manager", "cashier")
def staff_update_order_status(order_id):

    allowed_statuses = {
        "pending",
        "confirmed",
        "processing",
        "ready",
        "completed",
        "cancelled"
    }

    new_status = request.form.get(
        "status", ""
    ).strip().lower()

    if new_status not in allowed_statuses:
        flash("Invalid order status.", "error")
        return redirect("/staff/orders")

    try:
        with get_db() as db:

            if new_status == "completed":
                result = db.execute(
                    """
                    UPDATE online_orders
                    SET status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND business_id = %s
                      AND payment_status = 'paid'
                    RETURNING id
                    """,
                    (new_status, order_id, bid())
                ).fetchone()

                if not result:
                    flash(
                        "Cannot complete an unpaid order. "
                        "Confirm payment first.",
                        "error"
                    )
                    return redirect("/staff/orders")

            else:
                result = db.execute(
                    """
                    UPDATE online_orders
                    SET status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND business_id = %s
                    RETURNING id
                    """,
                    (new_status, order_id, bid())
                ).fetchone()

                if not result:
                    flash("Order not found.", "error")
                    return redirect("/staff/orders")

        flash(
            "Order status updated successfully.",
            "success"
        )

    except Exception:
        app.logger.exception("Order status update error")
        flash("Could not update order status.", "error")

    return redirect("/staff/orders")

# ============================================================
# STAFF ACCOUNT MANAGEMENT
# ============================================================

@app.route("/staff/users")
@role_required("owner")
def staff_users():

    try:
        with get_db() as db:
            users = db.execute(
                """
                SELECT name, username, role, created_at
                FROM users
                WHERE business_id = %s
                ORDER BY created_at DESC
                """,
                (bid(),)
            ).fetchall()

        return render_template(
            "staff_users.html",
            users=users,
            error=None
        )

    except Exception:
        app.logger.exception("Staff management loading error")
        flash("Could not load staff accounts.", "error")
        return redirect("/dashboard")


@app.route("/staff/users/add", methods=["POST"])
@role_required("owner")
def add_staff_user():

    name = request.form.get("name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not name or not username or not password:
        flash("Please fill in all cashier details.", "error")
        return redirect("/staff/users")

    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect("/staff/users")

    try:
        with get_db() as db:

            existing = db.execute(
                """
                SELECT id FROM users
                WHERE business_id = %s
                  AND LOWER(username) = LOWER(%s)
                """,
                (bid(), username)
            ).fetchone()

            if existing:
                flash("That username is already in use.", "error")
                return redirect("/staff/users")

            db.execute(
                """
                INSERT INTO users (
                    business_id,
                    name,
                    username,
                    password_hash,
                    role
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    bid(),
                    name,
                    username,
                    generate_password_hash(password),
                    "cashier"
                )
            )

        flash("Cashier account created successfully.", "success")
        return redirect("/staff/users")

    except Exception:
        app.logger.exception("Cashier account creation error")
        flash("Could not create cashier account.", "error")
        return redirect("/staff/users")


# ============================================================
# DASHBOARD
# ============================================================


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    business_id = bid()
    today = get_today()

    try:
        with get_db() as db:

            # Business name
            business = db.execute(
                """
                SELECT name
                FROM businesses
                WHERE id = %s
                """,
                (business_id,)
            ).fetchone()

            # Today's sales
            sales_result = db.execute(
                """
                SELECT
                    COALESCE(SUM(total_amount), 0) AS total
                FROM sales
                WHERE business_id = %s
                  AND (created_at AT TIME ZONE 'Africa/Nairobi')::date = %s
                """,
                (business_id, today)
            ).fetchone()

            # Today's expenses
            expenses_result = db.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE business_id = %s
                  AND (created_at AT TIME ZONE 'Africa/Nairobi')::date = %s
                """,
                (business_id, today)
            ).fetchone()

            # Stock value at buying price
            stock_result = db.execute(
                """
                SELECT
                    COALESCE(
                        SUM(stock_quantity * buying_price), 0
                    ) AS total
                FROM products
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            # Potential revenue at selling price
            potential_result = db.execute(
                """
                SELECT
                    COALESCE(
                        SUM(stock_quantity * selling_price), 0
                    ) AS total
                FROM products
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            # Total number of products
            count_result = db.execute(
                """
                SELECT COUNT(*) AS total
                FROM products
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            # Products running low
            low_stock = db.execute(
                """
                SELECT *
                FROM products
                WHERE business_id = %s
                  AND stock_quantity <= reorder_level
                ORDER BY stock_quantity ASC
                """,
                (business_id,)
            ).fetchall()

            # Five most recent sales
            recent_sales = db.execute(
                """
                SELECT *
                FROM sales
                WHERE business_id = %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (business_id,)
            ).fetchall()

            # Today's gross profit
            profit_result = db.execute(
                """
                SELECT
                    COALESCE(
                        SUM(
                            (si.unit_price - si.buying_price)
                            * si.quantity
                        ), 0
                    ) AS gross_profit
                FROM sale_items si
                JOIN sales s ON s.id = si.sale_id
                WHERE s.business_id = %s
                  AND (s.created_at AT TIME ZONE 'Africa/Nairobi')::date = %s
                """,
                (business_id, today)
            ).fetchone()
        sales = sales_result["total"]
        expenses = expenses_result["total"]
        gross_profit = profit_result["gross_profit"]

        return render_template(
            "dashboard.html",
            business_name=business["name"] if business else "Your Business",
            sales=sales,
            expenses=expenses,
            stock_value=stock_result["total"],
            potential_revenue=potential_result["total"],
            product_count=count_result["total"],
            low_stock=low_stock,
            recent_sales=recent_sales,
            profit=gross_profit - expenses,
            gross_profit=gross_profit
        )

    except Exception:
        app.logger.exception("Dashboard error")
        flash("Could not load the dashboard.", "error")
        abort(500)


# ============================================================
# PRODUCTS
# ============================================================

@app.route("/products")
@login_required
def products():

    business_id = bid()

    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    try:
        with get_db() as db:

            query = """
                SELECT *
                FROM products
                WHERE business_id = %s
            """

            params = [business_id]

            if search:
                query += " AND name ILIKE %s"
                params.append(f"%{search}%")

            if category:
                query += " AND category = %s"
                params.append(category)

            query += " ORDER BY name ASC"

            product_list = db.execute(
                query,
                tuple(params)
            ).fetchall()

            categories = db.execute(
                """
                SELECT DISTINCT category
                FROM products
                WHERE business_id = %s
                  AND category IS NOT NULL
                  AND category <> ''
                ORDER BY category
                """,
                (business_id,)
            ).fetchall()

        return render_template(
            "products.html",
            products=product_list,
            search=search,
            category=category,
            categories=categories
        )

    except Exception:
        app.logger.exception("Products loading error")
        flash("Could not load products.", "error")
        abort(500)


@app.route("/products/add", methods=["GET", "POST"])
@role_required("owner", "manager")
def add_product():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip() or None

        if not name:
            flash("Product name is required.", "error")
            return redirect("/products/add")

        try:
            buying_price = money_number(
                request.form.get("buying_price", "0"),
                "Buying price"
            )

            selling_price = money_number(
                request.form.get("selling_price", "0"),
                "Selling price"
            )

            stock_quantity = whole_number(
                request.form.get("stock_quantity", "0")
            )

            reorder_level = whole_number(
                request.form.get("reorder_level", "0")
            )

            if stock_quantity < 0 or reorder_level < 0:
                raise ValueError("Stock values cannot be negative.")

            with get_db() as db:

                product = db.execute(
                    """
                    INSERT INTO products (
                        business_id,
                        name,
                        category,
                        buying_price,
                        selling_price,
                        stock_quantity,
                        reorder_level
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        bid(),
                        name,
                        category,
                        buying_price,
                        selling_price,
                        stock_quantity,
                        reorder_level
                    )
                ).fetchone()

                if stock_quantity > 0:

                    db.execute(
                        """
                        INSERT INTO inventory_movements (
                            business_id,
                            product_id,
                            quantity_change,
                            movement_type
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            bid(),
                            product["id"],
                            stock_quantity,
                            "opening_stock"
                        )
                    )

            flash("Product added successfully.", "success")
            return redirect("/products")

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            app.logger.exception("Add product error")
            flash("Product could not be added.", "error")

    return render_template("product_form.html", product=None)


@app.route("/products/edit/<uuid:product_id>", methods=["GET", "POST"])
@role_required("owner", "manager")
def edit_product(product_id):

    try:
        with get_db() as db:

            product = db.execute(
                """
                SELECT *
                FROM products
                WHERE id = %s
                  AND business_id = %s
                """,
                (product_id, bid())
            ).fetchone()

            if not product:
                abort(404)

            if request.method == "POST":

                name = request.form.get("name", "").strip()
                category = (
                    request.form.get("category", "").strip() or None
                )

                if not name:
                    raise ValueError("Product name is required.")

                buying_price = money_number(
                    request.form.get("buying_price", "0"),
                    "Buying price"
                )

                selling_price = money_number(
                    request.form.get("selling_price", "0"),
                    "Selling price"
                )

                new_stock = whole_number(
                    request.form.get("stock_quantity", "0")
                )

                reorder_level = whole_number(
                    request.form.get("reorder_level", "0")
                )

                if new_stock < 0 or reorder_level < 0:
                    raise ValueError("Stock values cannot be negative.")

                old_stock = product["stock_quantity"]
                difference = new_stock - old_stock

                db.execute(
                    """
                    UPDATE products
                    SET
                        name = %s,
                        category = %s,
                        buying_price = %s,
                        selling_price = %s,
                        stock_quantity = %s,
                        reorder_level = %s
                    WHERE id = %s
                      AND business_id = %s
                    """,
                    (
                        name,
                        category,
                        buying_price,
                        selling_price,
                        new_stock,
                        reorder_level,
                        product_id,
                        bid()
                    )
                )

                if difference != 0:

                    db.execute(
                        """
                        INSERT INTO inventory_movements (
                            business_id,
                            product_id,
                            quantity_change,
                            movement_type
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            bid(),
                            product_id,
                            difference,
                            "stock_adjustment"
                        )
                    )

                flash("Product updated successfully.", "success")
                return redirect("/products")

        return render_template(
            "product_form.html",
            product=product
        )

    except ValueError as error:
        flash(str(error), "error")

        return render_template(
            "product_form.html",
            product=product
        )

    except Exception:
        app.logger.exception("Edit product error")
        abort(500)


@app.route("/products/delete/<uuid:product_id>", methods=["POST"])
@role_required("owner", "manager")
def delete_product(product_id):

    try:
        with get_db() as db:

            product = db.execute(
                """
                SELECT id
                FROM products
                WHERE id = %s
                  AND business_id = %s
                """,
                (product_id, bid())
            ).fetchone()

            if not product:
                abort(404)

            historical_sales = db.execute(
                """
                SELECT id
                FROM sale_items
                WHERE product_id = %s
                LIMIT 1
                """,
                (product_id,)
            ).fetchone()

            if historical_sales:
                flash(
                    "This product has sales history and cannot be deleted. "
                    "You can instead set its stock to zero.",
                    "error"
                )
                return redirect("/products")

            db.execute(
                """
                DELETE FROM inventory_movements
                WHERE product_id = %s
                  AND business_id = %s
                """,
                (product_id, bid())
            )

            db.execute(
                """
                DELETE FROM products
                WHERE id = %s
                  AND business_id = %s
                """,
                (product_id, bid())
            )

        flash("Product deleted successfully.", "success")

    except Exception:
        app.logger.exception("Delete product error")
        flash("Product could not be deleted.", "error")

    return redirect("/products")


# ============================================================
# POINT OF SALE
# ============================================================

@app.route("/pos")
@login_required
def pos():

    try:
        with get_db() as db:

            product_list = db.execute(
                """
                SELECT *
                FROM products
                WHERE business_id = %s
                  AND stock_quantity > 0
                ORDER BY name ASC
                """,
                (bid(),)
            ).fetchall()

        return render_template(
            "pos.html",
            products=product_list
        )

    except Exception:
        app.logger.exception("POS loading error")
        flash("Could not load the point of sale.", "error")
        abort(500)


@app.route("/pos/sale", methods=["POST"])
@login_required
def sale():

    items = request.form.getlist("product_id")
    quantities = request.form.getlist("quantity")

    if not items:
        flash("Add at least one product.", "error")
        return redirect("/pos")

    if len(items) != len(quantities):
        flash("Invalid sale details.", "error")
        return redirect("/pos")

    payment_method = request.form.get(
        "payment_method", "cash"
    ).strip().lower()

    allowed_methods = {"cash", "mpesa", "card"}

    if payment_method not in allowed_methods:
        flash("Invalid payment method.", "error")
        return redirect("/pos")

    try:
        # Combine duplicate products and validate UUIDs.
        quantities_by_product = {}

        for raw_id, raw_quantity in zip(items, quantities):

            product_id = safe_uuid(raw_id)
            quantity = whole_number(raw_quantity)

            if quantity < 1:
                raise ValueError("Quantity must be at least one.")

            quantities_by_product[product_id] = (
                quantities_by_product.get(product_id, 0) + quantity
            )

        total = Decimal("0")
        clean_items = []

        with get_db() as db:

            products_by_id = {}

            # Lock all products in consistent order.
            for product_id in sorted(quantities_by_product):

                product = db.execute(
                    """
                    SELECT *
                    FROM products
                    WHERE id = %s
                      AND business_id = %s
                    FOR UPDATE
                    """,
                    (product_id, bid())
                ).fetchone()

                if not product:
                    raise ValueError(
                        "A selected product was not found."
                    )

                quantity = quantities_by_product[product_id]

                if quantity > product["stock_quantity"]:
                    raise ValueError(
                        f"Insufficient stock for {product['name']}."
                    )

                products_by_id[product_id] = product

            # Calculate the total after stock validation.
            for product_id, quantity in quantities_by_product.items():

                product = products_by_id[product_id]

                total += product["selling_price"] * quantity

                clean_items.append((product, quantity))

            # Create the sale record.
            sale_id = db.execute(
                """
                INSERT INTO sales (
                    business_id,
                    total_amount,
                    payment_method,
                    client_transaction_id,
                    sync_status
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    bid(),
                    total,
                    payment_method,
                    uuid4(),
                    "synced"
                )
            ).fetchone()["id"]

            # Save each item and update stock.
            for product, quantity in clean_items:

                db.execute(
                    """
                    INSERT INTO sale_items (
                        sale_id,
                        product_id,
                        quantity,
                        unit_price,
                        buying_price
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        sale_id,
                        product["id"],
                        quantity,
                        product["selling_price"],
                        product["buying_price"]
                    )
                )

                db.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity - %s
                    WHERE id = %s
                      AND business_id = %s
                    """,
                    (
                        quantity,
                        product["id"],
                        bid()
                    )
                )

                db.execute(
                    """
                    INSERT INTO inventory_movements (
                        business_id,
                        product_id,
                        quantity_change,
                        movement_type,
                        reference_id
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        bid(),
                        product["id"],
                        -quantity,
                        "sale",
                        sale_id
                    )
                )

        flash(
            f"Sale completed: KSh {total:,.2f}.",
            "success"
        )

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        app.logger.exception("Sale processing error")
        flash(
            "Sale could not be completed. Please try again.",
            "error"
        )

    return redirect("/pos")



# ============================================================
# CUSTOMERS
# ============================================================

@app.route("/customers")
@login_required
def customers():

    business_id = bid()

    try:
        with get_db() as db:

            business = db.execute(
                """
                SELECT name
                FROM businesses
                WHERE id = %s
                """,
                (business_id,)
            ).fetchone()

            rows = db.execute(
                """
                SELECT *
                FROM customers
                WHERE business_id = %s
                ORDER BY name ASC
                """,
                (business_id,)
            ).fetchall()

        return render_template(
            "simple_list.html",
            business_name=business["name"] if business else "Your Business",
            title="Customers",
            subtitle="Manage your business customer directory.",
            rows=rows,
            fields=[
                ("name", "Customer Name"),
                ("phone", "Phone Number"),
                ("balance", "Balance")
            ],
            kind="customers"
        )

    except Exception:
        app.logger.exception("Customers loading error")
        flash("Could not load customers.", "error")
        abort(500)


@app.route("/customers/add", methods=["POST"])
@login_required
def add_customer():

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip() or None

    if not name:
        flash("Customer name is required.", "error")
        return redirect("/customers")

    try:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO customers (
                    business_id,
                    name,
                    phone,
                    balance
                )
                VALUES (%s, %s, %s, %s)
                """,
                (bid(), name, phone, Decimal("0"))
            )

        flash("Customer added successfully.", "success")

    except Exception:
        app.logger.exception("Add customer error")
        flash("Customer could not be added.", "error")

    return redirect("/customers")


# ============================================================
# SUPPLIERS
# ============================================================

@app.route("/suppliers")
@login_required
def suppliers():

    try:
        with get_db() as db:
            rows = db.execute(
                """
                SELECT name, phone, balance
                FROM suppliers
                WHERE business_id = %s
                ORDER BY name ASC
                """,
                (bid(),)
            ).fetchall()

        return render_template(
            "simple_list.html",
            title="Suppliers",
            subtitle="Manage your business supplier directory.",
            rows=rows,
            fields=[
                ("name", "Supplier Name"),
                ("phone", "Phone Number"),
                ("balance", "Balance")
            ],
            kind="suppliers"
        )

    except Exception:
        app.logger.exception("Suppliers loading error")
        abort(500)


@app.route("/suppliers/add", methods=["POST"])
@role_required("owner", "manager")
def add_supplier():

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip() or None

    if not name:
        flash("Supplier name is required.", "error")
        return redirect("/suppliers")

    try:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO suppliers (
                    business_id,
                    name,
                    phone,
                    balance
                )
                VALUES (%s, %s, %s, %s)
                """,
                (bid(), name, phone, Decimal("0"))
            )

        flash("Supplier added successfully.", "success")

    except Exception:
        app.logger.exception("Add supplier error")
        flash("Supplier could not be added.", "error")

    return redirect("/suppliers")


# ============================================================
# EXPENSES
# ============================================================

@app.route("/expenses")
@login_required
def expenses():

    business_id = bid()

    try:
        with get_db() as db:

            expense_list = db.execute(
                """
                SELECT *
                FROM expenses
                WHERE business_id = %s
                ORDER BY created_at DESC
                """,
                (business_id,)
            ).fetchall()

            total_result = db.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

        return render_template(
            "expenses.html",
            expenses=expense_list,
            rows=expense_list,
            total=total_result["total"]
        )

    except Exception:
        app.logger.exception("Expenses loading error")
        flash("Could not load expenses.", "error")
        abort(500)



@app.route("/expenses/add", methods=["GET", "POST"])
@role_required("owner", "manager")
def add_expense():

    if request.method == "POST":

        description = request.form.get(
            "description", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip() or None

        if not description:
            flash("Expense description is required.", "error")
            return redirect("/expenses/add")

        try:
            amount = money_number(
                request.form.get("amount", "0"),
                "Amount"
            )

            if amount <= 0:
                raise ValueError(
                    "Expense amount must be greater than zero."
                )

            with get_db() as db:
                db.execute(
                    """
                    INSERT INTO expenses (
                        business_id,
                        description,
                        amount,
                        category
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        bid(),
                        description,
                        amount,
                        category
                    )
                )

            flash("Expense recorded successfully.", "success")
            return redirect("/expenses")

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            app.logger.exception("Add expense error")
            flash("Expense could not be recorded.", "error")

    return render_template(
        "expenses.html",
        expenses=[],
        rows=[],
        total=Decimal("0")
    )



# ============================================================
# REPORTS
# ============================================================

@app.route("/reports")
@role_required("owner", "manager")
def reports():

    business_id = bid()

    try:
        with get_db() as db:

            business = db.execute(
                """
                SELECT name
                FROM businesses
                WHERE id = %s
                """,
                (business_id,)
            ).fetchone()

            sales_result = db.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(SUM(total_amount), 0) AS total
                FROM sales
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            expenses_result = db.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            stock_result = db.execute(
                """
                SELECT
                    COUNT(*) AS products,
                    COALESCE(
                        SUM(stock_quantity * buying_price), 0
                    ) AS value
                FROM products
                WHERE business_id = %s
                """,
                (business_id,)
            ).fetchone()

            payment_rows = db.execute(
                """
                SELECT
                    LOWER(payment_method) AS payment_method,
                    COUNT(*) AS count,
                    COALESCE(SUM(total_amount), 0) AS total
                FROM sales
                WHERE business_id = %s
                GROUP BY LOWER(payment_method)
                """,
                (business_id,)
            ).fetchall()

            profit_result = db.execute(
                """
                SELECT
                    COALESCE(
                        SUM(
                            (si.unit_price - si.buying_price)
                            * si.quantity
                        ), 0
                    ) AS gross_profit
                FROM sale_items si
                JOIN sales s ON s.id = si.sale_id
                WHERE s.business_id = %s
                """,
                (business_id,)
            ).fetchone()

        payment_summary = {
            "cash": {"count": 0, "total": Decimal("0")},
            "mpesa": {"count": 0, "total": Decimal("0")},
            "card": {"count": 0, "total": Decimal("0")}
        }

        for row in payment_rows:
            method = (
                row["payment_method"] or "cash"
            ).strip().lower()

            if method in payment_summary:
                payment_summary[method] = {
                    "count": row["count"],
                    "total": row["total"]
                }

        gross_profit = profit_result["gross_profit"]
        net_profit = gross_profit - expenses_result["total"]

        return render_template(
            "reports.html",
            business_name=business["name"] if business else "Your Business",
            sales=sales_result,
            expenses=expenses_result,
            stock=stock_result,
            payment_summary=payment_summary,
            sales_count=sales_result["count"],
            expenses_count=expenses_result["count"],
            gross_profit=gross_profit,
            net_profit=net_profit
        )

    except Exception:
        app.logger.exception("Reports loading error")
        flash("Could not load reports.", "error")
        abort(500)



# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(403)
def forbidden(error):
    return "You do not have permission to access this page.", 403


@app.errorhandler(404)
def not_found(error):
    return "The requested page or record was not found.", 404


@app.errorhandler(500)
def internal_error(error):
    return "An internal error occurred. Please try again.", 500


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
