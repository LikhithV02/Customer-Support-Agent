from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Money = Numeric(10, 2, asdecimal=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def TZDateTime() -> DateTime:  # noqa: N802 - reads like a type
    return DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    loyalty_tier: Mapped[str] = mapped_column(String, default="standard")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, default="general")
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String, default="delivered")
    order_date: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    delivered_date: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    is_final_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="orders")


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        # Hard backstop against double refunds under concurrency: at most one
        # *approved* refund row can ever exist per order.
        Index(
            "uq_refunds_one_approved_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("decision = 'approved'"),
            sqlite_where=text("decision = 'approved'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)  # approved | denied | escalated
    reason: Mapped[str] = mapped_column(String, default="")
    decided_by: Mapped[str] = mapped_column(String, default="agent")  # agent | human
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_customer_created", "customer_id", "created_at"),
        Index("ix_conversations_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    # Monotonic per-conversation event counter (atomically incremented).
    event_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Cumulative LLM tokens, for the per-conversation budget.
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class ReasoningEvent(Base):
    __tablename__ = "reasoning_events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_reasoning_events_conv_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    # tool_call | tool_result | policy_eval | decision | injection_flag | model | usage | ...
    step_type: Mapped[str] = mapped_column(String, nullable=False)
    node: Mapped[str] = mapped_column(String, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class ConversationArchive(Base):
    """A conversation's full trace, kept after its live rows are purged.

    The retention job writes one row per conversation before it deletes a
    demo sandbox (see `app/maintenance/archive.py`), so attacks on the public
    demo stay reviewable for `RETENTION_DAYS`. Self-contained: no foreign keys,
    because the customer, orders and messages it describes are gone.
    """

    __tablename__ = "conversation_archive"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(TZDateTime(), index=True)
    archived_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    # Refund rows written in this conversation: [{order_id, scenario, decision, amount}]
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    # Triage tags derived from the trace, e.g. ["injection", "output_corrected"]
    flags: Mapped[list] = mapped_column(JSON, default=list)
    # Ground-truth violations: [{kind, detail}]. Empty means none were found.
    breaches: Mapped[list] = mapped_column(JSON, default=list)
    breach: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    opik_trace_ids: Mapped[list] = mapped_column(JSON, default=list)
    # {"orders": [...], "messages": [...], "events": [...]}
    transcript: Mapped[dict] = mapped_column(JSON, default=dict)
