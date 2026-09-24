"""LangGraph agent: a tool-calling ReAct loop.

The graph has two nodes — `agent` (the chat model bound to the refund tools) and
`tools` (executes the calls) — looping until the model produces a final answer.
The tools embody the fetch -> validate -> decide phases, and the deterministic
policy gate inside them is what makes the agent safe regardless of model output.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.llm import get_chat_model, get_fallback_model, get_model
from app.agent.tools import TOOLS


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# One compiled graph per (model, fallback) pair — i.e. one per process in
# production. Compiling per request was a major CPU cost under load.
_cache: dict[bool, tuple] = {}


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
    model_with_tools = model.bind_tools(tools)
    if fallback is not None:
        # Tools must be bound on each model before composing fallbacks.
        model_with_tools = model_with_tools.with_fallbacks([fallback.bind_tools(tools)])
    tool_node = ToolNode(tools)

    async def agent_node(state: AgentState) -> dict:
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

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
