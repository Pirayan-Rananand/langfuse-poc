from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from money_coach.state import State


class ClarificationDecision(BaseModel):
    needs_clarification: bool = Field(
        description="True if critical financial numbers are missing and the tools cannot be used accurately without them."
    )
    questions: list[str] = Field(
        description="Targeted follow-up questions. Empty list when needs_clarification is False."
    )


def build_clarifier(llm: BaseChatModel, system_prompt: str):
    """Chain that decides if the user's request has enough context for financial advice.

    Uses PydanticOutputParser (prompt-based JSON) rather than tool-calling structured
    output — works reliably across all OpenRouter-proxied models.

    Input:  {"messages": list[BaseMessage]}
    Output: ClarificationDecision
    """
    parser = PydanticOutputParser(pydantic_object=ClarificationDecision)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt + "\n\n{format_instructions}"),
            ("placeholder", "{messages}"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    return prompt | llm | parser


class ClarifyNode:
    def __init__(self, clarifier_chain) -> None:
        self._chain = clarifier_chain

    def __call__(self, state: State, config: RunnableConfig) -> dict:
        try:
            decision = self._chain.invoke(
                {"messages": state["messages"]}, config=config
            )
        except Exception:
            # Never block the user if the clarifier fails (e.g. malformed JSON)
            return {"needs_clarification": False}

        if decision.needs_clarification:
            questions = "\n".join(f"- {q}" for q in decision.questions)
            reply = (
                "Before I can give you accurate advice, I need a bit more detail:"
                f"\n\n{questions}"
            )
            return {
                "messages": [AIMessage(content=reply)],
                "needs_clarification": True,
            }

        return {"needs_clarification": False}
