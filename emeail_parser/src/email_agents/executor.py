from typing import Iterator, Any
from .shared_state import SharedState

class GraphExecutor:
    def __init__(self, graph: Any):  # generic compiled graph callable
        self.graph = graph

    def run(self, state: SharedState) -> SharedState:
        # Execute full graph
        result_state = self.graph.invoke(state)
        # Newer langgraph may return a dict state; wrap if necessary
        if isinstance(result_state, dict) and not isinstance(result_state, SharedState):
            result_state = SharedState(**{**state.model_dump(), **result_state})
        return result_state

    def stream(self, state: SharedState) -> Iterator[SharedState]:
        for step in self.graph.stream(state):
            if isinstance(step, dict) and not isinstance(step, SharedState):
                step = SharedState(**{**state.model_dump(), **step})
            yield step
