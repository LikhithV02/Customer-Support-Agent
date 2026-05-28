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

from app.agent.llm import get_chat_model
from app.agent.tools import ToolContext, build_tools


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent(ctx: ToolContext):
    model = get_chat_model()
    tools = build_tools(ctx)
    model_with_tools = model.bind_tools(tools)
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
