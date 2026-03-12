from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser


class ClarificationDecision(BaseModel):
    needs_clarification: bool = Field(
        description="True if critical financial numbers are missing and the tools cannot be used accurately without them."
    )
    questions: list[str] = Field(
        description="Targeted follow-up questions. Empty list when needs_clarification is False."
    )


def build_clarifier(llm: BaseChatModel, system_prompt: str):
    """Return a chain that evaluates whether the user's context is sufficient.

    Uses PydanticOutputParser (prompt-based JSON) instead of tool-calling
    structured output, so it works reliably across all OpenRouter models.

    Input:  {"messages": list[BaseMessage]}
    Output: ClarificationDecision
    """
    parser = PydanticOutputParser(pydantic_object=ClarificationDecision)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system_prompt + "\n\n{format_instructions}",
            ),
            ("placeholder", "{messages}"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    return prompt | llm | parser
