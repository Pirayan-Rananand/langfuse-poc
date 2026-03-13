from langchain_core.runnables import RunnableConfig

from money_coach.state import State


class CoachNode:
    def __init__(self, coach_graph) -> None:
        self._graph = coach_graph

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        result = self._graph.invoke({"messages": state["messages"]}, config=config)
        return {"messages": result["messages"]}
