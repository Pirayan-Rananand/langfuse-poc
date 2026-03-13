from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


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
