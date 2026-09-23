from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import get_settings

settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        # 写操作立即获取 RESERVED 锁并等待，避免并发选课/退课时的写写竞争
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        # BEGIN IMMEDIATE：事务一开始即持写锁，临界区串行化，杜绝空位被并发抢走
        conn.exec_driver_sql("BEGIN IMMEDIATE")


def _ensure_column(inspector, table: str, column: str, ddl_type: str) -> None:
    """已存在的旧库补齐新列（create_all 不会修改既有表）。"""
    if inspector.has_table(table):
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column not in columns:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    # 候补队列：选课状态 + 单调排队序号；存量选课记录一律视为已入选
    _ensure_column(inspector, "enrollments", "status", "VARCHAR(11) NOT NULL DEFAULT 'ENROLLED'")
    _ensure_column(inspector, "enrollments", "waitlist_position", "INTEGER")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
