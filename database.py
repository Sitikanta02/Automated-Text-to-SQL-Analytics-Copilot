"""
database.py
-----------
Owns the database connection, the schema (SQLAlchemy models), and a
setup routine that creates the tables and fills them with realistic
mock e-commerce data.

Swap SQLite for Postgres by changing DATABASE_URL (see README).
"""

import os
import random
from datetime import datetime, timedelta

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------

# For SQLite: "sqlite:///./ecommerce.db"
# For Postgres: "postgresql+psycopg2://user:password@localhost:5432/ecommerce"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ecommerce.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Schema: 4 related tables (customers, products, orders, order_items)
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    city = Column(String(60), nullable=False)
    country = Column(String(60), nullable=False)
    signup_date = Column(DateTime, nullable=False)

    orders = relationship("Order", back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(120), nullable=False)
    category = Column(String(60), nullable=False)
    unit_price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, nullable=False)

    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    order_date = Column(DateTime, nullable=False)
    status = Column(String(30), nullable=False)  # e.g. delivered, shipped, cancelled

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    """Line items — this is what makes orders <-> products a proper
    many-to-many relationship, and gives the LLM a realistic join to
    reason about (a common real-world schema pattern)."""

    __tablename__ = "order_items"

    order_item_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


# ---------------------------------------------------------------------------
# Mock data generation
# ---------------------------------------------------------------------------

CITIES = [
    ("Mumbai", "India"), ("Bengaluru", "India"), ("Delhi", "India"),
    ("New York", "USA"), ("San Francisco", "USA"), ("London", "UK"),
    ("Berlin", "Germany"), ("Toronto", "Canada"), ("Sydney", "Australia"),
    ("Singapore", "Singapore"),
]

FIRST_NAMES = ["Aarav", "Priya", "John", "Emma", "Liam", "Sofia", "Chen",
               "Yuki", "Omar", "Fatima", "Noah", "Ava", "Rohan", "Maya"]
LAST_NAMES = ["Sharma", "Patel", "Smith", "Johnson", "Müller", "Garcia",
              "Wang", "Tanaka", "Khan", "Ali", "Brown", "Singh"]

CATEGORIES = {
    "Electronics": ["Wireless Mouse", "Mechanical Keyboard", "USB-C Hub",
                    "Bluetooth Speaker", "27-inch Monitor", "Webcam HD"],
    "Home & Kitchen": ["Air Fryer", "Coffee Maker", "Blender", "Toaster",
                       "Vacuum Cleaner", "Cookware Set"],
    "Books": ["Data Science Handbook", "Clean Code", "Atomic Habits",
              "The Pragmatic Programmer", "Sapiens", "Deep Work"],
    "Apparel": ["Cotton T-Shirt", "Running Shoes", "Denim Jacket",
                "Wool Sweater", "Sports Cap", "Rain Jacket"],
    "Sports": ["Yoga Mat", "Dumbbell Set", "Cycling Helmet",
               "Tennis Racket", "Football", "Resistance Bands"],
}

ORDER_STATUSES = ["delivered", "shipped", "processing", "cancelled", "returned"]


def _random_date(days_back: int) -> datetime:
    return datetime.now() - timedelta(days=random.randint(0, days_back))


def seed_data(session, num_customers=40, num_orders=150):
    """Populate the tables with deterministic-ish mock data. Safe to call
    only when tables are empty (checked by caller)."""

    # --- Customers ---
    customers = []
    for i in range(num_customers):
        city, country = random.choice(CITIES)
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        customer = Customer(
            full_name=name,
            email=f"{name.lower().replace(' ', '.')}{i}@example.com",
            city=city,
            country=country,
            signup_date=_random_date(730),
        )
        customers.append(customer)
    session.add_all(customers)
    session.flush()  # assign PKs

    # --- Products ---
    products = []
    for category, names in CATEGORIES.items():
        for name in names:
            products.append(Product(
                product_name=name,
                category=category,
                unit_price=round(random.uniform(9.99, 499.99), 2),
                stock_quantity=random.randint(0, 500),
            ))
    session.add_all(products)
    session.flush()

    # --- Orders + Order Items ---
    for _ in range(num_orders):
        customer = random.choice(customers)
        order = Order(
            customer_id=customer.customer_id,
            order_date=_random_date(365),
            status=random.choice(ORDER_STATUSES),
        )
        session.add(order)
        session.flush()

        for _ in range(random.randint(1, 4)):
            product = random.choice(products)
            session.add(OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=random.randint(1, 5),
                price_at_purchase=product.unit_price,
            ))

    session.commit()


def init_db():
    """Create all tables, then seed mock data if the DB is empty.
    Idempotent — safe to call every time the app starts."""

    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        existing = session.query(Customer).first()
        if existing is None:
            seed_data(session)
            print("[database] Mock e-commerce data seeded.")
        else:
            print("[database] Existing data found, skipping seed.")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
