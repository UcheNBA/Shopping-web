from flask import Flask, render_template, session, redirect, url_for, request, jsonify, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_wtf import CSRFProtect
import os
import json
import sqlite3
import datetime
import re
import click
import time
import secrets
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ================= APP SETUP =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
csrf = CSRFProtect(app)

# Configure Cloudinary using environment variables for security
cloudinary.config(
  cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"),
  api_key = os.environ.get("CLOUDINARY_API_KEY"),
  api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
  secure=True
)


# Ensure the landing splash is the first thing a visitor sees.
@app.before_request
def ensure_landing_first():
    # only enforce for GET requests (so form POSTs still work)
    path = request.path or ''
    if request.method != 'GET':
        return None
    # allow if session or persistent cookie indicates user already saw the landing
    if session.get('seen_landing') or request.cookies.get('seen_splash'):
        return None
    # allow landing itself and static/admin/api resources
    if path == '/' or path.startswith('/static') or path.startswith('/admin') or path.startswith('/api') or path.startswith('/favicon.ico'):
        return None
    # otherwise redirect anonymous visitor to landing first
    return redirect(url_for('index'))

# ================= PATHS =================

DB_PATH = os.path.join(BASE_DIR, "data.db")

# ================= DB =================


def get_db():
    # increase timeout to reduce 'database is locked' errors under concurrent access
    # allow access across threads for the dev server
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_connection():
    return get_db()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        email TEXT,
        full_name TEXT,
        age INTEGER,
        dob TEXT,
        state TEXT,
        country TEXT,
        address TEXT,
        phone TEXT,
        created_at TEXT
    )""")

    # Admin users
    cur.execute("""CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT
    )""")

    # Products
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT,
        price REAL,
        description TEXT,
        category TEXT,
        image TEXT,
        rating REAL
    )""")

    # Carts
    cur.execute("""CREATE TABLE IF NOT EXISTS carts (
        user_id INTEGER PRIMARY KEY,
        cart_json TEXT
    )""")

    # Orders
    cur.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        total REAL,
        status TEXT,
        payment_method TEXT,
        proof TEXT,
        created_at TEXT,
        proof_uploaded_at TEXT
    )""")

    # Order Items
    cur.execute("""CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        price REAL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")

    # Reviews
    cur.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY,
        product_id INTEGER,
        user_id INTEGER,
        order_id INTEGER,
        rating INTEGER,
        comment TEXT,
        created_at TEXT,
        FOREIGN KEY(product_id) REFERENCES products(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # Wishlists
    cur.execute("""CREATE TABLE IF NOT EXISTS wishlists (
        user_id INTEGER PRIMARY KEY,
        product_ids TEXT
    )""")

    # Notifications
    cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        message TEXT,
        seen INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    conn.commit()
    conn.close()


init_db()

# ================= MIGRATIONS =================
def migrate_db():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN reset_token_expiry TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

migrate_db()


def bootstrap_admin_from_env():
    username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not username and not password:
        return
    if not username or not password:
        raise RuntimeError("Both admin bootstrap environment variables are required")
    if len(password) < 12:
        raise RuntimeError("Admin bootstrap password must be at least 12 characters")

    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        admin = conn.execute(
            "SELECT id FROM admin_users WHERE username = ?", (username,)
        ).fetchone()
        if admin:
            conn.execute(
                "UPDATE admin_users SET password_hash = ? WHERE username = ?",
                (password_hash, username),
            )
        else:
            conn.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
        conn.commit()
    finally:
        conn.close()
    print("Admin bootstrap credentials applied.")


bootstrap_admin_from_env()

# ================= HELPERS =================


def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrap


def ensure_cart():
    if "cart" not in session:
        session["cart"] = {}

# --- DB helpers ---


def fetch_all_products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_all_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_db(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(p) if p else None


def add_product_db(name, description, price, image_path=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (name, price, description, category, image, rating) VALUES (?,?,?,?,?,?)",
                (name, price, description, None, image_path, 5.0))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_product_db(product_id, name=None, description=None, price=None, image_path=None, category=None):
    conn = get_db()
    cur = conn.cursor()
    updates = []
    values = []
    if name is not None:
        updates.append("name=?")
        values.append(name)
    if description is not None:
        updates.append("description=?")
        values.append(description)
    if price is not None:
        updates.append("price=?")
        values.append(price)
    if image_path is not None:
        updates.append("image=?")
        values.append(image_path)
    if category is not None:
        updates.append("category=?")
        values.append(category)
    if updates:
        cur.execute(
            f"UPDATE products SET {','.join(updates)} WHERE id=?", (*values, product_id))
        conn.commit()
    conn.close()


def delete_product_db(product_id):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

# --- Cart helpers ---


def get_cart_for_user(uid):
    conn = get_db()
    r = conn.execute(
        "SELECT cart_json FROM carts WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return json.loads(r["cart_json"]) if r and r["cart_json"] else {}


def save_cart_for_user(uid, cart):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO carts VALUES (?,?)",
                 (uid, json.dumps(cart)))
    conn.commit()
    conn.close()


def delete_cart_for_user(uid):
    conn = get_db()
    conn.execute("DELETE FROM carts WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()


def get_wishlist_for_user(uid):
    conn = get_db()
    r = conn.execute(
        "SELECT product_ids FROM wishlists WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return json.loads(r["product_ids"]) if r and r["product_ids"] else []


def save_wishlist_for_user(uid, wishlist):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO wishlists VALUES (?,?)",
                 (uid, json.dumps(wishlist)))
    conn.commit()
    conn.close()


def calculate_cart_total(uid):
    cart = get_cart_for_user(uid)
    total = 0.0
    for pid, qty in cart.items():
        p = get_product_db(int(pid))
        if p:
            total += p["price"] * qty
    return round(total, 2)


def create_order(uid, total, method):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (user_id,total,status,payment_method,created_at)
        VALUES (?,?,?,?,?)
    """, (uid, total, "PENDING_PAYMENT", method, datetime.datetime.utcnow()))
    conn.commit()
    oid = cur.lastrowid
    conn.close()
    return oid


def mark_order_paid(order_id):
    conn = get_db()
    try:
        conn.execute("UPDATE orders SET status='PAID' WHERE id=?", (order_id,))
        conn.commit()
    finally:
        conn.close()


def add_notification(user_id, message):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO notifications (user_id, message, seen, created_at) VALUES (?,?,?,?)",
                    (user_id, message, 0, datetime.datetime.utcnow()))
        conn.commit()
    finally:
        conn.close()


def fetch_notifications_for_user(uid):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC', (uid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notifications_seen(uid):
    conn = get_db()
    conn.execute('UPDATE notifications SET seen=1 WHERE user_id=?', (uid,))
    conn.commit()
    conn.close()


def delete_notification_db(nid, uid):
    conn = get_db()
    try:
        conn.execute("DELETE FROM notifications WHERE id=? AND user_id=?", (nid, uid))
        conn.commit()
    finally:
        conn.close()

# ================= AUTH =================


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (u,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], p):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["cart"] = get_cart_for_user(user["id"])
            # Force the splash screen to show on next visit to '/'
            session.pop('seen_landing', None)
            resp = make_response(redirect(url_for('index')))
            resp.delete_cookie('seen_splash')
            return resp
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        form = request.form
        password_hash = generate_password_hash(form["password"])
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO users (username, password_hash, full_name, email, age, dob, state, country, address, phone, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                form.get('username'), password_hash, form.get('full_name'), form.get('email'),
                form.get('age'), form.get('dob'), form.get('state'), form.get('country'),
                form.get('address'), form.get('phone'), datetime.datetime.utcnow()
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            # This happens if the username is already taken
            conn.close()
            return render_template("register.html", error="Username already exists.")
        finally:
            conn.close()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        
        if user:
            token = secrets.token_urlsafe(32)
            # Token valid for 1 hour
            expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            conn.execute("UPDATE users SET reset_token=?, reset_token_expiry=? WHERE id=?", 
                         (token, expiry, user['id']))
            conn.commit()
            
            reset_link = url_for('reset_password', token=token, _external=True)
            
            # --- SEND EMAIL via GMAIL SMTP (Free) ---
            # Generate App Password at: https://myaccount.google.com/apppasswords
            sender_email = os.environ.get("MAIL_USERNAME", "prosperonyekwere04@gmail.com")
            sender_password = os.environ.get("MAIL_PASSWORD", "asax qbtf xwpt ikhu")
            
            try:
                user_name = user['full_name'] or user['username']
                html_content = f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                    <h2 style="color: #0C4A6E;">Password Reset Request</h2>
                    <p>Hello {user_name},</p>
                    <p>We received a request to reset the password for your account. You can reset your password by clicking the button below:</p>
                    <p style="text-align: center;">
                        <a href="{reset_link}" style="background-color: #0EA5E9; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; display: inline-block;">Reset Your Password</a>
                    </p>
                    <p>If the button doesn't work, you can copy and paste the following link into your browser:</p>
                    <p style="word-break: break-all;">
                        <a href="{reset_link}">{reset_link}</a>
                    </p>
                    <p>This link is valid for one hour. If you did not request a password reset, please ignore this email.</p>
                    <hr style="border: none; border-top: 1px solid #eee;" />
                    <p style="font-size: 0.9em; color: #64748B;">
                        Thanks,<br>
                        LOL SHOPPING TEAM
                    </p>
                </div>
                """
                
                # Create a MIMEText object with HTML content
                msg = MIMEText(html_content, 'html')
                
                msg['Subject'] = 'Your Password Reset Link from My Shop'
                msg['From'] = sender_email
                msg['To'] = email
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, email, msg.as_string())
                
                conn.close()
                return render_template("forgot_password.html", success="Check your email for the reset link.")
            except Exception as e:
                print(f"Error sending email: {e}")
                print(f"\n[DEBUG] FALLBACK LINK: {reset_link}\n")
                conn.close()
                return render_template("forgot_password.html", error="Could not send email (check console for link).")
        
        conn.close()
        # Show same message to prevent email enumeration
        return render_template("forgot_password.html", success="Check your email (or console) for the reset link.")
        
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE reset_token=?", (token,)).fetchone()
    
    # Basic validation: check if user exists and token hasn't expired
    if not user or not user['reset_token_expiry'] or datetime.datetime.utcnow() > datetime.datetime.strptime(user['reset_token_expiry'], '%Y-%m-%d %H:%M:%S.%f'):
        conn.close()
        return render_template("reset_password.html", error="Invalid or expired token.")

    if request.method == "POST":
        password = request.form.get("password")
        hashed = generate_password_hash(password)
        conn.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_token_expiry=NULL WHERE id=?", (hashed, user['id']))
        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html", token=token)

# ================= SHOP =================


@app.route("/")
def index():
    # Show the landing page once per session; subsequent visits go into the app
    if not (session.get('seen_landing') or request.cookies.get('seen_splash')):
        session['seen_landing'] = True
        resp = make_response(render_template("landing.html"))
        # persist the splash seen state for a long time (1 year)
        resp.set_cookie('seen_splash', '1', max_age=60 * 60 * 24 * 365)
        return resp

    # If they've seen the splash, just send them to the shop.
    return redirect(url_for('shop'))


@app.route('/shop')
def shop():
    # Search and Filter logic
    query = request.args.get('q')
    category = request.args.get('category')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    sort = request.args.get('sort')

    conn = get_db()
    sql = "SELECT * FROM products WHERE 1=1"
    params = []

    if query:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    if category:
        sql += " AND category = ?"
        params.append(category)
    if min_price:
        sql += " AND price >= ?"
        params.append(min_price)
    if max_price:
        sql += " AND price <= ?"
        params.append(max_price)
    
    # Add sorting logic
    if sort == 'price_asc':
        sql += " ORDER BY price ASC"
    elif sort == 'price_desc':
        sql += " ORDER BY price DESC"
    else: # default sort
        sql += " ORDER BY id DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    products = [dict(r) for r in rows]

    return render_template('index.html', products=products)


@app.route('/about')
def about():
    """Renders the about us page."""
    return render_template('about.html')


@app.route('/contact')
def contact():
    """Renders the contact us page."""
    return render_template('contact.html')

@app.route('/faq')
def faq():
    """Renders the FAQ page."""
    return render_template('faq.html')

@app.route('/terms')
def terms():
    """Renders the terms of service page."""
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    """Renders the privacy policy page."""
    return render_template('privacy.html')


@app.route('/product/<int:product_id>')
def product(product_id):
    """Renders the product detail page."""
    product = get_product_db(product_id)
    if not product:
        return "Product not found", 404
    return render_template('product.html', product=product)

@app.route("/add_to_cart", methods=["POST"])
@login_required
def add_to_cart():
    ensure_cart()
    pid = request.form.get("product_id")
    qty = int(request.form.get("quantity", 1))
    cart = session["cart"]
    cart[str(pid)] = cart.get(str(pid), 0) + qty
    session["cart"] = cart
    save_cart_for_user(session["user_id"], cart)
    # Redirect back to the page the user was on, so they can continue shopping
    return redirect(request.referrer or url_for('shop'))


@app.route("/remove_from_cart", methods=["POST"])
@login_required
def remove_from_cart():
    ensure_cart()
    pid = request.form.get("product_id")
    cart = session["cart"]
    if pid in cart:
        cart.pop(pid)
        session["cart"] = cart
        save_cart_for_user(session["user_id"], cart)
    return redirect(url_for("cart"))

# ================= WISHLIST =================


@app.route("/wishlist")
@login_required
def wishlist():
    product_ids = get_wishlist_for_user(session["user_id"])
    products = []
    if product_ids:
        for pid in product_ids:
            p = get_product_db(pid)
            if p:
                products.append(p)
    return render_template("wishlist.html", products=products)


@app.route("/wishlist/add", methods=["POST"])
@login_required
def add_to_wishlist():
    pid = int(request.form.get("product_id"))
    wishlist = get_wishlist_for_user(session["user_id"])
    if pid not in wishlist:
        wishlist.append(pid)
        save_wishlist_for_user(session["user_id"], wishlist)
    return redirect(request.referrer or url_for('shop'))


@app.route("/wishlist/remove", methods=["POST"])
@login_required
def remove_from_wishlist():
    pid = int(request.form.get("product_id"))
    wishlist = get_wishlist_for_user(session["user_id"])
    if pid in wishlist:
        wishlist.remove(pid)
        save_wishlist_for_user(session["user_id"], wishlist)
    # Redirect back to wishlist page if removing from there, otherwise back to wherever user was
    if request.referrer and 'wishlist' in request.referrer:
        return redirect(url_for('wishlist'))
    return redirect(request.referrer or url_for('shop'))

# ================= CART =================


@app.route("/cart")
@login_required
def cart():
    ensure_cart()
    cart_data = session.get("cart", {})
    items = []
    total = 0.0
    for pid_str, qty in cart_data.items():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        product = get_product_db(pid)
        if not product:
            continue
        subtotal = product["price"] * qty
        total += subtotal
        items.append(
            {"product": product, "quantity": qty, "subtotal": subtotal})
    return render_template("cart.html", items=items, total=total)

# ================= CHECKOUT =================


@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    uid = session["user_id"]
    cart = get_cart_for_user(uid)
    method = request.form.get("payment_method")

    if not cart:
        return redirect(url_for("cart"))

    total = calculate_cart_total(uid)
    if total <= 0:
        return redirect(url_for("cart"))

    order_id = create_order(uid, total, method)

    # Save order items from the cart
    conn = get_db()
    cur = conn.cursor()
    for pid, qty in cart.items():
        product = get_product_db(int(pid))
        if product:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (order_id, int(pid), qty, product['price']))
    conn.commit()
    conn.close()

    # Clear the cart
    delete_cart_for_user(uid)
    session['cart'] = {}
    return redirect(url_for("pay_bank", order_id=order_id))

# ================= BANK TRANSFER =================


@app.route("/pay/bank/<int:order_id>/")
@login_required
def pay_bank(order_id):
    return render_template("bank_transfer.html", order_id=order_id)


@app.route("/upload-proof/<int:order_id>", methods=["POST"])
@login_required
def upload_proof(order_id):
    file = request.files.get("proof")
    if not file or file.filename == "":
        return "No file uploaded", 400

    try:
        # Upload the file to a folder named 'payment_proofs' in Cloudinary
        upload_result = cloudinary.uploader.upload(file, folder="payment_proofs", public_id=f"order_{order_id}")
        image_url = upload_result.get('secure_url')
    except Exception as e:
        print(f"Error uploading to Cloudinary: {e}")
        return "Failed to upload proof.", 500

    conn = get_db()
    conn.execute("UPDATE orders SET proof=?, proof_uploaded_at=? WHERE id=?", (image_url, datetime.datetime.utcnow(), order_id))
    conn.commit()

    conn.close()

    return render_template("waiting.html")


@app.route("/admin/payment-proofs")
@admin_required
def payment_proofs():
    conn = get_db()
    # Join orders with users to get the username
    orders = conn.execute("""
        SELECT o.*, u.username AS user_name
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.id DESC
    """).fetchall()
    conn.close()
    return render_template("payment_proofs.html", orders=orders)


# ================= LOGOUT =================
@app.route("/logout")
@login_required
def logout():
    user_id = session.get("user_id")
    if user_id:
        delete_cart_for_user(user_id)
    session.clear()
    return redirect(url_for("login"))

# ================= PROFILE =================


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?",
                        (session["user_id"],)).fetchone()
    error = None
    success = None
    if request.method == "POST":
        try:
            full_name = request.form.get("full_name") or ''
            email = request.form.get("email") or ''
            age = request.form.get("age") or ''
            dob = request.form.get("dob") or ''
            state = request.form.get("state") or ''
            country = request.form.get("country") or ''
            address = request.form.get("address") or ''
            phone = request.form.get("phone") or ''
            conn.execute("""
                UPDATE users
                SET full_name=?, email=?, age=?, dob=?, state=?, country=?, address=?, phone=?
                WHERE id=?
            """, (full_name, email, age, dob, state, country, address, phone, session["user_id"]))
            conn.commit()
            success = "Profile updated successfully!"
            user = conn.execute("SELECT * FROM users WHERE id=?",
                                (session["user_id"],)).fetchone()
        except Exception as e:
            error = "Failed to update profile: " + str(e)
    conn.close()
    return render_template("profile.html", user=user, error=error, success=success)

# ================= API =================


@app.route('/my_orders')
@login_required
def my_orders():
    conn = get_db()
    orders_rows = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (session['user_id'],)).fetchall()
    
    orders = []
    for order_row in orders_rows:
        order = dict(order_row)
        # Fetch items and review status for each order
        items_rows = conn.execute("""
            SELECT oi.*, p.name, p.image,
                   (SELECT 1 FROM reviews r WHERE r.order_id = oi.order_id AND r.product_id = oi.product_id) as has_review
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        """, (order['id'],)).fetchall()
        order['order_items'] = [dict(item) for item in items_rows]
        orders.append(order)
        
    conn.close()
    return render_template('my_orders.html', orders=orders)


@app.route("/track/<int:order_id>")
@login_required
def track_order(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, session["user_id"])).fetchone()
    conn.close()
    if not order:
        return redirect(url_for("my_orders"))
    return render_template("track_order.html", order=order)

@app.route("/order/cancel/<int:order_id>", methods=["POST"])
@login_required
def cancel_order(order_id):
    conn = get_db()
    # Only allow cancellation if status is PENDING_PAYMENT
    order = conn.execute("SELECT id FROM orders WHERE id=? AND user_id=? AND status='PENDING_PAYMENT'", 
                         (order_id, session["user_id"])).fetchone()
    if order:
        conn.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
        conn.commit()
    conn.close()
    return redirect(url_for("my_orders"))

@app.route('/review/product/<int:product_id>/order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def add_review(product_id, order_id):
    conn = get_db()

    # Security check: ensure the user owns this delivered order and it contains this product
    order = conn.execute("""
        SELECT o.id FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.id = ? AND o.user_id = ? AND oi.product_id = ? AND o.status = 'DELIVERED'
    """, (order_id, session['user_id'], product_id)).fetchone()

    if not order:
        return redirect(url_for('my_orders'))

    # Check if review already exists
    if conn.execute("SELECT id FROM reviews WHERE order_id=? AND product_id=?", (order_id, product_id)).fetchone():
        return redirect(url_for('my_orders'))

    product = get_product_db(product_id)

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment', '')

        if not rating:
            return render_template('add_review.html', product=product, order_id=order_id, error="Rating is required.")

        # Insert the new review
        conn.execute("""
            INSERT INTO reviews (product_id, user_id, order_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (product_id, session['user_id'], order_id, int(rating), comment, datetime.datetime.utcnow()))
        conn.commit()

        # Update the product's average rating
        avg_rating_row = conn.execute("SELECT AVG(rating) as avg_r FROM reviews WHERE product_id=?", (product_id,)).fetchone()
        if avg_rating_row and avg_rating_row['avg_r']:
            conn.execute("UPDATE products SET rating=? WHERE id=?", (avg_rating_row['avg_r'], product_id))
            conn.commit()

        conn.close()
        add_notification(session['user_id'], f"Thank you for reviewing {product['name']}!")
        return redirect(url_for('my_orders'))

    conn.close()
    return render_template('add_review.html', product=product, order_id=order_id)


@app.route("/api/products")
def api_products():
    return jsonify(fetch_all_products())

# ================= ADMIN =================


@app.route("/admin/all-orders")
@admin_required
def all_orders():
    return redirect(url_for('payment_proofs'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        row = conn.execute(
            'SELECT * FROM admin_users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password_hash'], password):
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    products = fetch_all_products()
    users = fetch_all_users()
    conn = get_db()
    orders = conn.execute("""
        SELECT o.*, u.username AS user_name
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.status = 'PENDING_PAYMENT'
        ORDER BY o.id DESC
    """).fetchall()
    conn.close()
    return render_template('admin_dashboard.html', products=products, users=users, orders=orders)


@app.route('/admin/add_product', methods=['POST'])
@admin_required
def admin_add_product():
    name = request.form.get('name')
    desc = request.form.get('description', '')
    category = request.form.get('category')
    try:
        price = float(request.form.get('price', '0'))
    except ValueError:
        price = 0.0
    new_id = add_product_db(name, desc, price, None)
    # Update category immediately after add since add_product_db signature in this version didn't take it
    if category:
        update_product_db(new_id, category=category)

    file = request.files.get('image')
    if file and file.filename and allowed_file(file.filename):
        try:
            # Upload to Cloudinary, using the product ID for a unique public ID
            upload_result = cloudinary.uploader.upload(file, folder="products", public_id=f"product_{new_id}")
            image_url = upload_result.get('secure_url')
            update_product_db(new_id, image_path=image_url)
        except Exception as e:
            print(f"Error uploading product image to Cloudinary: {e}")
            # Continue without an image if upload fails
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit(product_id):
    p = get_product_db(product_id)
    if not p:
        return "Product not found", 404
    if request.method == 'POST':
        name = request.form.get('name', p['name'])
        description = request.form.get('description', p.get('description', ''))
        category = request.form.get('category')
        try:
            price = float(request.form.get('price', p['price']))
        except ValueError:
            price = p['price']
        file = request.files.get('image')
        image_path = None
        if file and file.filename and allowed_file(file.filename):
            try:
                # Upload new image, overwriting the old one by using the same public_id
                upload_result = cloudinary.uploader.upload(file, folder="products", public_id=f"product_{p['id']}")
                image_path = upload_result.get('secure_url') # This will be the new URL
            except Exception as e:
                print(f"Error uploading edited product image: {e}")
                image_path = p.get('image') # Keep old image if upload fails
        update_product_db(
            p['id'], name=name, description=description, price=price, image_path=image_path, category=category, rating=p.get('rating'))
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_edit.html', product=p)


@app.route('/admin/delete', methods=['POST'])
@admin_required
def admin_delete():
    pid = request.form.get('product_id')
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return redirect(url_for('admin_dashboard'))
    prod = get_product_db(pid)
    delete_product_db(pid)
    # Also delete the image from Cloudinary
    try:
        cloudinary.uploader.destroy(f"products/product_{pid}")
    except Exception as e:
        print(f"Could not delete image from Cloudinary: {e}")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_user', methods=['POST'])
@admin_required
def admin_delete_user():
    uid = request.form.get('user_id')
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return redirect(url_for('admin_dashboard'))
    try:
        delete_cart_for_user(uid)
    except Exception:
        pass
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

# ================= ADMIN CLI =================


@app.cli.command('create-admin')
@click.argument('username')
@click.argument('password')
def create_admin(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    pw_hash = generate_password_hash(password)
    cur.execute('SELECT id FROM admin_users WHERE username = ?', (username,))
    row = cur.fetchone()
    if row:
        cur.execute(
            'UPDATE admin_users SET password_hash = ? WHERE username = ?', (pw_hash, username))
        print(f'Updated password for admin user: {username}')
    else:
        cur.execute(
            'INSERT INTO admin_users (username, password_hash) VALUES (?, ?)', (username, pw_hash))
        print(f'Created admin user: {username}')
    conn.commit()
    conn.close()


@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE status='PENDING_PAYMENT'").fetchall()
    conn.close()
    return render_template("admin_orders.html", orders=orders)


@app.route("/admin/orders/approve/<int:order_id>", methods=["GET", "POST"])
@admin_required
def approve_order(order_id):
    # Support POST (AJAX) and GET
    conn = get_db()
    row = conn.execute(
        'SELECT user_id FROM orders WHERE id=?', (order_id,)).fetchone()
    conn.close()
    uid = row['user_id'] if row else None
    # try to mark paid and add notification with retry on locked DB
    attempts = 0
    while True:
        try:
            mark_order_paid(order_id)
            if uid:
                add_notification(
                    uid, f"Your payment for order #{order_id} has been approved and is now being prepared for shipping.")
            break
        except sqlite3.OperationalError:
            attempts += 1
            if attempts >= 5:
                return jsonify({'ok': False, 'error': 'database locked'}), 500
            time.sleep(0.1)
    if request.method == 'POST':
        return jsonify({'ok': True, 'order_id': order_id})
    return redirect(url_for("admin_orders"))


@app.route("/admin/orders/reject/<int:order_id>", methods=["GET", "POST"])
@admin_required
def reject_order(order_id):
    conn = get_db()
    row = conn.execute(
        'SELECT user_id FROM orders WHERE id=?', (order_id,)).fetchone()
    uid = row['user_id'] if row else None
    attempts = 0
    while True:
        try:
            conn.execute(
                "UPDATE orders SET status='REJECTED' WHERE id=?", (order_id,))
            conn.commit()
            conn.close()
            break
        except sqlite3.OperationalError:
            attempts += 1
            if attempts >= 5:
                try:
                    conn.close()
                except Exception:
                    pass
                return jsonify({'ok': False, 'error': 'database locked'}), 500
            time.sleep(0.1)
    if uid:
        # add_notification may also encounter a locked DB; retry inside
        attempts = 0
        while True:
            try:
                add_notification(
                    uid, f"Your payment for order #{order_id} was rejected. Please double-check the payment details and re-upload your proof, or contact us if you need help.")
                break
            except sqlite3.OperationalError:
                attempts += 1
                if attempts >= 5:
                    return jsonify({'ok': False, 'error': 'database locked'}), 500
                time.sleep(0.1)
    if request.method == 'POST':
        return jsonify({'ok': True, 'order_id': order_id})
    return redirect(url_for('admin_orders'))


@app.route("/admin/orders/ship/<int:order_id>", methods=["POST"])
@admin_required
def ship_order(order_id):
    conn = get_db()
    try:
        row = conn.execute('SELECT user_id FROM orders WHERE id=?', (order_id,)).fetchone()
        uid = row['user_id'] if row else None
        
        attempts = 0
        success = False
        while attempts < 5:
            try:
                conn.execute("UPDATE orders SET status='SHIPPED' WHERE id=?", (order_id,))
                conn.commit()
                success = True
                break
            except sqlite3.OperationalError:
                attempts += 1
                time.sleep(0.1)
    finally:
        conn.close()

    if not success:
        return jsonify({'ok': False, 'error': 'database locked'}), 500

    if uid:
        add_notification(uid, f"Great news! Your order #{order_id} has been shipped and is on its way.")
        
    return jsonify({'ok': True})


@app.route("/admin/orders/deliver/<int:order_id>", methods=["POST"])
@admin_required
def deliver_order(order_id):
    conn = get_db()
    try:
        row = conn.execute('SELECT user_id FROM orders WHERE id=?', (order_id,)).fetchone()
        uid = row['user_id'] if row else None
        
        attempts = 0
        success = False
        while attempts < 5:
            try:
                conn.execute("UPDATE orders SET status='DELIVERED' WHERE id=?", (order_id,))
                conn.commit()
                success = True
                break
            except sqlite3.OperationalError:
                attempts += 1
                time.sleep(0.1)
    finally:
        conn.close()

    if not success:
        return jsonify({'ok': False, 'error': 'database locked'}), 500

    if uid:
        add_notification(uid, f"Your order #{order_id} has been delivered. Thank you for shopping with us!")
        
    return jsonify({'ok': True})


@app.route('/notifications')
@login_required
def notifications():
    uid = session.get('user_id')
    notes = fetch_notifications_for_user(uid)
    # mark as seen
    mark_notifications_seen(uid)
    return render_template('notifications.html', notifications=notes)


@app.route("/notifications/delete/<int:nid>", methods=["POST"])
@login_required
def delete_notification(nid):
    delete_notification_db(nid, session["user_id"])
    return redirect(url_for("notifications"))


@app.context_processor
def inject_notification_count():
    uid = session.get('user_id')
    unseen = 0
    wishlist_ids = []
    cart_item_count = 0
    if uid:
        wishlist_ids = get_wishlist_for_user(uid)
        cart_item_count = len(session.get('cart', {}))
        conn = get_db()
        try:
            row = conn.execute(
                'SELECT COUNT(*) AS c FROM notifications WHERE user_id=? AND seen=0', (uid,)).fetchone()
            unseen = row['c'] if row else 0
        finally:
            conn.close()
    return dict(notifications_unseen_count=unseen, current_year=datetime.datetime.now().year, 
                wishlist_ids=wishlist_ids, cart_item_count=cart_item_count)



# ================= CHATBOT =================
class Chatbot:
    def __init__(self):
        self.responses = {
            "hi": "Hello there! 😊 How can I help you shop today?",
            "hello": "Hi! Welcome to My Shop. What can I do for you?",
            "hey": "Hey! Looking for something special?",
            "good morning": "Good morning! ☀️ I hope you're having a great day. How can I help?",
            "good afternoon": "Good afternoon! Ready to find some great deals?",
            "good evening": "Good evening! Let me know if you need help finding anything.",
            "how are you": "I'm doing great, thanks for asking! 🤖 Ready to assist you.",
            "what is your name": "I'm Uche, your personal shopping assistant.",
            "who are you": "I'm Uche, here to help you navigate our store.",
            "help": "I'm here to help! You can ask about order status, payments, returns, or our contact info.",
            "bye": "Goodbye! Come back soon! 👋",
            "thank you": "You're very welcome! Happy shopping! 🛍️",
            "thanks": "No problem at all! Let me know if you need anything else.",
            "track order": "You can track your order from the 'My Orders' page in your profile.",
            "payment options": "We currently accept Bank Transfer. You can find details during checkout.",
            "return policy": "We have a 7-day return policy for defective items. Please contact support."
        }

    def get_response(self, user_input, user_id=None):
        user_input = user_input.lower().strip().rstrip('?.!')

        # Check for order tracking intent
        if 'track' in user_input and 'order' in user_input:
            if not user_id:
                return "Please log in to track your order."
            
            # Try to find an order number in the message
            match = re.search(r'\d+', user_input)
            if not match:
                return "Please provide your order number, like 'track my order 123'."
            
            order_id = int(match.group(0))
            conn = get_db()
            order = conn.execute("SELECT status FROM orders WHERE id=? AND user_id=?", (order_id, user_id)).fetchone()
            conn.close()

            if order:
                status = order['status'].replace('_', ' ').title()
                return f"The status of your order #{order_id} is: {status}. Let me know if you need anything else!"
            else:
                return f"Sorry, I couldn't find order #{order_id} associated with your account. Please double-check the ID."

        # Exact match check
        if user_input in self.responses:
            return self.responses[user_input]
            
        # Fuzzy keyword matching
        if 'thank' in user_input:
            return self.responses['thank you']
            
        if 'ship' in user_input or 'delivery' in user_input:
            return "We offer fast nationwide shipping! 🚚 Delivery usually takes 2-5 business days."
            
        if 'contact' in user_input or 'support' in user_input or 'phone' in user_input or 'email' in user_input:
             return "You can reach our support team at 08145929790 or email prosperonyekwere04@gmail.com."

        if 'payment' in user_input or 'pay' in user_input:
            return self.responses['payment options']

        if 'return' in user_input or 'refund' in user_input:
            return self.responses['return policy']
            
        if 'location' in user_input or 'address' in user_input or 'where' in user_input:
            return "We operate online and ship directly to your doorstep nationwide!"

        # Category-based recommendations
        # We check 'women' before 'men' to avoid matching 'men' inside the word 'women'
        category_map = [
            ('women', 'women'), ('woman', 'women'),
            ('men', 'men'), ('man', 'men'),
            ('bags', 'bags'), ('bag', 'bags'),
            ('sports', 'sports'), ('sport', 'sports'),
            ('musical', 'musical'), ('music', 'musical'),
            ('kids', 'kids'), ('kid', 'kids')
        ]
        
        for keyword, db_cat in category_map:
            if keyword in user_input:
                conn = get_db()
                products = conn.execute("SELECT id, name, price FROM products WHERE category=? ORDER BY rating DESC LIMIT 3", (db_cat,)).fetchall()
                conn.close()
                if products:
                    items = [f"<a href='/product/{p['id']}'>{p['name']}</a> (₦{p['price']:,.2f})" for p in products]
                    return f"Here are our top picks for {db_cat}:<br>" + "<br>".join(items)

        # General recommendations
        if 'recommend' in user_input or 'suggest' in user_input or 'best' in user_input or 'buy' in user_input or 'product' in user_input:
            conn = get_db()
            products = conn.execute("SELECT id, name, price FROM products ORDER BY rating DESC LIMIT 3").fetchall()
            conn.close()
            if products:
                items = [f"<a href='/product/{p['id']}'>{p['name']}</a> (₦{p['price']:,.2f})" for p in products]
                return f"Check out our highly rated products:<br>" + "<br>".join(items)

        return "I'm not quite sure about that one, but I'm learning! 🤔 You can ask for 'help', 'contact info', or 'track order'."

chatbot_instance = Chatbot()

@app.route("/chatbot/message", methods=["POST"])
def chatbot_message():
    uid = session.get("user_id")
    message = request.json.get("message", "")
    response = chatbot_instance.get_response(message, user_id=uid)
    return jsonify({"response": response})



if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "False").lower() in ["true", "1", "t"])
