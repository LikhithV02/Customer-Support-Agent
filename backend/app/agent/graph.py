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

from app.agent.llm import get_chat_model, get_fallback_model
from app.agent.tools import TOOLS


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# One compiled graph per (model, fallback) pair — i.e. one per process in
# production. Compiling per request was a major CPU cost under load.
_cache: tuple | None = None


def get_agent():
    """Return the compiled agent graph for the current model, building it once.

    Per-request state (the verified customer) is passed at invoke time via
    `config["configurable"]["tool_ctx"]` — see `app.agent.tools.tool_config`.
    """
    global _cache
    model = get_chat_model()
    fallback = get_fallback_model()
    if _cache is not None and _cache[0] is model and _cache[1] is fallback:
        return _cache[2]
    agent = _compile(model, fallback)
    _cache = (model, fallback, agent)
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
