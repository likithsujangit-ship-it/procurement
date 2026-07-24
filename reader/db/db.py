import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Resolve db directory relative to reader root
DB_DIR = Path(__file__).parent.resolve()
DB_FILE = DB_DIR / "rfq_platform.db"

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_FILE.as_posix()}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)


def init_db(schema_path: str = None):
    if schema_path is None:
        schema_path = str(DB_DIR / "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        raw = f.read()
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
    schema_sql = "\n".join(lines)
    with engine.begin() as conn:
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    print(f"Database ready at: {DATABASE_URL}")


def get_session():
    return SessionLocal()


def get_or_create_supplier(name: str, email: str = None) -> int:
    session = get_session()
    try:
        row = session.execute(
            text("SELECT id FROM suppliers WHERE name = :name"), {"name": name}
        ).fetchone()
        if row:
            return row[0]
        result = session.execute(
            text("INSERT INTO suppliers (name, email) VALUES (:name, :email)"),
            {"name": name, "email": email},
        )
        session.commit()
        return result.lastrowid
    finally:
        session.close()


def get_or_create_rfq(rfq_number: str, part_description: str = None) -> int:
    session = get_session()
    try:
        row = session.execute(
            text("SELECT id FROM rfqs WHERE rfq_number = :n"), {"n": rfq_number}
        ).fetchone()
        if row:
            return row[0]
        result = session.execute(
            text("INSERT INTO rfqs (rfq_number, part_description) VALUES (:n, :d)"),
            {"n": rfq_number, "d": part_description},
        )
        session.commit()
        return result.lastrowid
    finally:
        session.close()


def insert_quotation(rfq_id: int, supplier_id: int, extracted_fields: dict) -> int:
    session = get_session()
    try:
        # Check if the quotation already exists to avoid duplicate entries for the same RFQ and Supplier
        row = session.execute(
            text("SELECT id FROM quotations WHERE rfq_id = :rfq_id AND supplier_id = :supplier_id"),
            {"rfq_id": rfq_id, "supplier_id": supplier_id}
        ).fetchone()
        if row:
            return row[0]

        result = session.execute(
            text("""
                INSERT INTO quotations
                    (rfq_id, supplier_id, price, currency, moq, lead_time_days,
                     payment_terms, validity, raw_extraction_json, confidence_score)
                VALUES
                    (:rfq_id, :supplier_id, :price, :currency, :moq, :lead_time_days,
                     :payment_terms, :validity, :raw_json, :confidence)
            """),
            {
                "rfq_id": rfq_id,
                "supplier_id": supplier_id,
                "price": extracted_fields.get("price"),
                "currency": extracted_fields.get("currency", "INR"),
                "moq": extracted_fields.get("moq"),
                "lead_time_days": extracted_fields.get("lead_time_days"),
                "payment_terms": extracted_fields.get("payment_terms"),
                "validity": extracted_fields.get("validity"),
                "raw_json": str(extracted_fields),
                "confidence": extracted_fields.get("confidence_score", 0.0),
            },
        )
        session.commit()
        return result.lastrowid
    finally:
        session.close()


def get_comparison_grid(rfq_number: str):
    session = get_session()
    try:
        result = session.execute(
            text("""
                SELECT s.name AS supplier, q.price, q.currency, q.moq,
                       q.lead_time_days, q.payment_terms, q.confidence_score
                FROM quotations q
                JOIN suppliers s ON s.id = q.supplier_id
                JOIN rfqs r ON r.id = q.rfq_id
                WHERE r.rfq_number = :rfq_number
                ORDER BY q.price ASC
            """),
            {"rfq_number": rfq_number},
        )
        return [dict(row._mapping) for row in result]
    finally:
        session.close()
