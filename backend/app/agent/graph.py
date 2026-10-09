"""LangGraph agent: a tool-calling ReAct loop.

The graph has two nodes — `agent` (the chat model bound to the refund tools) and
`tools` (executes the calls) — looping until the model produces a final answer.
The tools embody the fetch -> validate -> decide phases, and the deterministic
policy gate inside them is what makes the agent safe regardless of model output.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.llm import get_chat_model, get_fallback_model, get_model
from app.agent.tools import TOOLS
from app.config import get_settings
from app.observability import log_event

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# One compiled graph per (model, fallback) pair — i.e. one per process in
# production. Compiling per request was a major CPU cost under load.
_cache: dict[bool, tuple] = {}


class PrimaryBreaker:
    """Per-process circuit breaker for the primary model.

    After the primary fails, calls go straight to the fallback for
    `LLM_FALLBACK_COOLDOWN_S`, then the primary is tried again. Without it,
    every model call in a turn would wait out the primary's timeout first.
    """

    def __init__(self):
        self.open_until = 0.0

    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def trip(self, exc: Exception) -> None:
        cooldown = get_settings().llm_fallback_cooldown_s
        self.open_until = time.monotonic() + cooldown
        log_event(
            logger,
            "primary model failed; using fallback",
            level=logging.WARNING,
            error_type=type(exc).__name__,
            cooldown_s=cooldown,
        )


breaker = PrimaryBreaker()


def get_agent(scripted: bool = False):
    """Return the compiled agent graph for the current model, building it once.

    `scripted=True` runs on the deterministic `fake` model instead — the public
    demo switches to it when its token budget is spent, so the demo keeps
    working at zero cost.

    Per-request state (the verified customer) is passed at invoke time via
    `config["configurable"]["tool_ctx"]` — see `app.agent.tools.tool_config`.
    """
    if scripted:
        model, fallback = get_model("fake"), None
    else:
        model, fallback = get_chat_model(), get_fallback_model()
    cached = _cache.get(scripted)
    if cached is not None and cached[0] is model and cached[1] is fallback:
        return cached[2]
    agent = _compile(model, fallback)
    _cache[scripted] = (model, fallback, agent)
    return agent


def _compile(model, fallback):
    tools = TOOLS
    primary = model.bind_tools(tools)
    secondary = fallback.bind_tools(tools) if fallback is not None else None
    tool_node = ToolNode(tools)

    async def agent_node(state: AgentState) -> dict:
        messages = state["messages"]
        if secondary is None:
            return {"messages": [await primary.ainvoke(messages)]}
        if not breaker.is_open():
            try:
                return {"messages": [await primary.ainvoke(messages)]}
            except Exception as exc:  # provider error, timeout, unreachable proxy
                breaker.trip(exc)
        return {"messages": [await secondary.ainvoke(messages)]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
