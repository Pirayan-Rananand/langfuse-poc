from pydantic import BaseModel


class PromptConfig(BaseModel):
    instruction: str


class AgentConfig(BaseModel):
    name: str
    model: str
    prompts: PromptConfig


class AgentsConfig(BaseModel):
    emotional_gate: AgentConfig
    comfort: AgentConfig
    welcome: AgentConfig
    debt_inventory: AgentConfig
    cash_flow: AgentConfig
    triage: AgentConfig
    strategy_builder: AgentConfig
    escalate: AgentConfig


class AppConfig(BaseModel):
    agents: AgentsConfig
