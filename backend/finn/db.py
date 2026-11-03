"""Persistence: a small SQLite schema (PostgreSQL-compatible via FINN_DB_URL).

Datetimes are stored as naive UTC everywhere; the API emits ISO strings with 'Z'
and the frontend renders them in Asia/Kolkata.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import DB_URL

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    sector: Mapped[str] = mapped_column(String(80), default="")
    bse_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    in_portfolio: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str | None] = mapped_column(String(8), nullable=True)            # stock | etf
    asset_class: Mapped[str | None] = mapped_column(String(20), nullable=True)    # Equity | Debt | Gold | International
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)            # % of the mock portfolio
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)                # tracks, underlying index, notes
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    identity_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)  # e.g. ["portfolio.yaml", "bse_lookup"]
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceBar(Base):
    __tablename__ = "price_bars"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD (exchange date)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="yfinance")


class Announcement(Base):
    __tablename__ = "announcements"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # BSE NEWSID
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    headline: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    bse_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bse_subcategory: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attachment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="unclassified")
    category_method: Mapped[str] = mapped_column(String(16), default="rule")  # rule | llm | default
    base_score: Mapped[int] = mapped_column(Integer, default=0)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enrichment_status: Mapped[str] = mapped_column(String(16), default="none")  # none|ok|failed|unsupported
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KV(Base):
    """Small JSON blobs: preferences, refresh stamps, screener snapshots, research cache."""
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AlertRule(Base):
    """An investor-defined condition. symbol=None means the whole portfolio."""
    __tablename__ = "alert_rules"
    __table_args__ = {"sqlite_autoincrement": True}  # never reuse a deleted rule's id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, default="")  # generated descriptions can exceed 120 chars (Postgres enforces lengths)
    profile: Mapped[str | None] = mapped_column(String(40), nullable=True, default="demo")  # owner; single demo profile for now
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # price_move | volume | filing
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)  # either | up | down (price_move)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)  # % for price, x for volume
    window: Mapped[int | None] = mapped_column(Integer, nullable=True)  # volume lookback sessions
    categories: Mapped[list | None] = mapped_column(JSON, nullable=True)  # filing
    min_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)  # routine | worth_a_look | needs_you
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Alert(Base):
    """A rule that fired. dedupe_key makes evaluation idempotent: one alert per rule x company x session/filing."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # market | filing
    session_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    announcement_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(8), default="medium")  # high | medium
    title: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class LLMCall(Base):
    """Every model response, keyed by a hash of model + prompt + inputs. Doubles as the cost ledger."""
    __tablename__ = "llm_calls"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(60), default="")
    response: Mapped[Any] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # sha1(url)[:16]
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # annual_report | transcript | filing
    title: Mapped[str] = mapped_column(String(300), default="")
    period: Mapped[str] = mapped_column(String(40), default="")  # "Jul 2025" (call month) / "FY2025"
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|ok|scanned|failed
    pages: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DocPage(Base):
    __tablename__ = "doc_pages"
    doc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1-based, matches PDF viewers
    text: Mapped[str] = mapped_column(Text, default="")


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Additive schema evolution: new nullable columns are added to existing tables so a committed
    finn.db from an older build keeps working. (Destructive changes would need a real migration.)"""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'))


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def kv_get(s: Session, key: str, default: Any = None) -> Any:
    row = s.get(KV, key)
    return row.value if row else default


def kv_get_row(s: Session, key: str) -> KV | None:
    return s.get(KV, key)


def kv_set(s: Session, key: str, value: Any) -> None:
    row = s.get(KV, key)
    if row:
        row.value = value
        row.updated_at = utcnow()
    else:
        s.add(KV(key=key, value=value, updated_at=utcnow()))


def portfolio_symbols(s: Session) -> list[str]:
    return list(s.scalars(select(Company.symbol).where(Company.in_portfolio.is_(True)).order_by(Company.symbol)))
