import json

import pytest
from sqlalchemy import select

from app.agent.tools import ToolContext, build_tools
from app.db.models import Refund
from tests.conftest import tools_by_name


def _ctx(session, customer_id=None) -> ToolContext:
    return ToolContext(
        session=session, conversation_id="conv-test", verified_customer_id=customer_id
    )


async def _call(tools, name, **kwargs):
    return json.loads(await tools_by_name(tools)[name].ainvoke(kwargs))


def approved_refunds(session, order_id):
    return session.scalars(
        select(Refund).where(
            Refund.order_id == order_id, Refund.decision == "approved"
        )
    ).all()


@pytest.mark.asyncio
async def test_lookup_sets_identity_and_lists_orders(db_session):
    ctx = _ctx(db_session)
    tools = build_tools(ctx)
    res = await _call(tools, "lookup_customer", email="alice@example.com")
    assert res["found"] is True
    assert ctx.verified_customer_id == "CUST-001"
    orders = await _call(tools, "list_orders")
    assert any(o["order_id"] == "ORD-1001" for o in orders["orders"])


@pytest.mark.asyncio
async def test_get_order_requires_identity(db_session):
    tools = build_tools(_ctx(db_session))
    res = await _call(tools, "get_order", order_id="ORD-1001")
    assert res["error"] == "identity_not_verified"


@pytest.mark.asyncio
async def test_ownership_mismatch_is_refused(db_session):
    # Verified as Alice (CUST-001), try to read Carol's order (CUST-003).
    tools = build_tools(_ctx(db_session, customer_id="CUST-001"))
    res = await _call(tools, "get_order", order_id="ORD-1003")
    assert res["error"] == "ownership_mismatch"


@pytest.mark.asyncio
async def test_issue_refund_approves_valid_order(db_session):
    tools = build_tools(_ctx(db_session, customer_id="CUST-001"))
    res = await _call(tools, "issue_refund", order_id="ORD-1001")
    assert res["decision"] == "approved"
    assert len(approved_refunds(db_session, "ORD-1001")) == 1


@pytest.mark.asyncio
async def test_issue_refund_blocks_final_sale(db_session):
    # ORD-1002 is final sale → must never become an approved refund.
    tools = build_tools(_ctx(db_session, customer_id="CUST-002"))
    res = await _call(tools, "issue_refund", order_id="ORD-1002")
    assert res["decision"] == "denied"
    assert approved_refunds(db_session, "ORD-1002") == []


@pytest.mark.asyncio
async def test_issue_refund_escalates_high_value(db_session):
    # ORD-1003 is $1299 → escalated, never auto-approved.
    tools = build_tools(_ctx(db_session, customer_id="CUST-003"))
    res = await _call(tools, "issue_refund", order_id="ORD-1003")
    assert res["decision"] == "escalated"
    assert approved_refunds(db_session, "ORD-1003") == []


@pytest.mark.asyncio
async def test_issue_refund_blocks_already_refunded(db_session):
    tools = build_tools(_ctx(db_session, customer_id="CUST-004"))
    res = await _call(tools, "issue_refund", order_id="ORD-1004")
    assert res["decision"] == "denied"


@pytest.mark.asyncio
async def test_issue_refund_blocks_out_of_window(db_session):
    tools = build_tools(_ctx(db_session, customer_id="CUST-005"))
    res = await _call(tools, "issue_refund", order_id="ORD-1005")
    assert res["decision"] == "denied"


@pytest.mark.asyncio
async def test_check_eligibility_does_not_write_refund(db_session):
    tools = build_tools(_ctx(db_session, customer_id="CUST-001"))
    res = await _call(tools, "check_refund_eligibility", order_id="ORD-1001")
    assert res["decision"] == "approved"
    # No refund row should have been created by a read-only eligibility check.
    all_refunds = db_session.scalars(
        select(Refund).where(Refund.order_id == "ORD-1001")
    ).all()
    assert all_refunds == []
