from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from money_coach.state import State


class ComfortNode:
    def __init__(self, llm: BaseChatModel, system_prompt: str) -> None:
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("placeholder", "{messages}"),
        ])
        self._chain = prompt | llm

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        response = self._chain.invoke(
            {"messages": state["messages"]}, config=config
        )
        return {
            "messages": [AIMessage(content=response.content)],
            "emotional_state": "unknown",  # reset so next turn re-checks
        }
