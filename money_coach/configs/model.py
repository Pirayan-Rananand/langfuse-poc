from pydantic import BaseModel
from typing import Optional


class PromptConfig(BaseModel):
    instruction: str


class AgentConfig(BaseModel):
    name: str
    model: str
    prompts: PromptConfig


class AgentsConfig(BaseModel):
    clarifier: AgentConfig
    main: AgentConfig


class AppConfig(BaseModel):
    agents: AgentsConfig
