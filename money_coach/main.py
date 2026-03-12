"""CLI smoke-test loop for the Money Coach agent.

Usage:
    uv run python -m money_coach.main
"""

from dotenv import load_dotenv

load_dotenv()

from money_coach.agent import graph  # noqa: E402 – must come after load_dotenv
from money_coach.dependencies import get_langfuse_handler, langfuse_client  # noqa: E402

from typing import Any, Dict
from uuid import UUID
import json
import base64

import httpx
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import FastAPI, HTTPException, Body


class GitHubSettings(BaseSettings):
    """GitHub repository configuration."""

    GITHUB_TOKEN: str
    GITHUB_REPO_OWNER: str
    GITHUB_REPO_NAME: str
    GITHUB_FILE_PATH: str = "langfuse_prompt.json"
    GITHUB_BRANCH: str = "main"
    REQUIRED_LABEL: str = ""  # Optional: only sync prompts with this label

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )


config = GitHubSettings()


class LangfuseEvent(BaseModel):
    """Langfuse webhook event structure."""

    id: UUID = Field(description="Event identifier")
    timestamp: str = Field(description="Event timestamp")
    type: str = Field(description="Event type")
    action: str = Field(description="Performed action")
    prompt: Dict[str, Any] = Field(description="Prompt content")


async def sync(event: LangfuseEvent) -> Dict[str, Any]:
    """Synchronize prompt data to GitHub repository."""
    # Check if prompt has required label (if specified)
    if config.REQUIRED_LABEL:
        prompt_labels = event.prompt.get("labels", [])
        if config.REQUIRED_LABEL not in prompt_labels:
            return {
                "skipped": f"Prompt does not have required label '{config.REQUIRED_LABEL}'"
            }

    api_endpoint = f"https://api.github.com/repos/{config.GITHUB_REPO_OWNER}/{config.GITHUB_REPO_NAME}/contents/{config.GITHUB_FILE_PATH}"

    request_headers = {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    content_json = json.dumps(event.prompt, indent=2)
    encoded_content = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")

    name = event.prompt.get("name", "unnamed")
    version = event.prompt.get("version", "unknown")
    message = f"{event.action}: {name} v{version}"

    payload = {
        "message": message,
        "content": encoded_content,
        "branch": config.GITHUB_BRANCH,
    }

    async with httpx.AsyncClient() as http_client:
        try:
            existing = await http_client.get(
                api_endpoint,
                headers=request_headers,
                params={"ref": config.GITHUB_BRANCH},
            )
            if existing.status_code == 200:
                payload["sha"] = existing.json().get("sha")
        except Exception:
            pass

        try:
            response = await http_client.put(
                api_endpoint, headers=request_headers, json=payload
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Repository sync failed: {str(e)}"
            )


app = FastAPI(title="Langfuse GitHub Sync", version="1.0")


@app.post("/webhook/prompt", status_code=201)
async def receive_webhook(event: LangfuseEvent = Body(...)):
    """Process Langfuse webhook and sync to GitHub."""
    result = await sync(event)
    return {
        "status": "synced",
        "commit_info": result.get("commit", {}),
        "file_info": result.get("content", {}),
    }


@app.get("/status")
async def health_status():
    """Service health check."""
    return {"healthy": True}


def main():
    print("Money Coach CLI — type 'quit' or 'exit' to stop.\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        if not user_input:
            continue

        result = graph.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"callbacks": [get_langfuse_handler()]},
        )
        langfuse_client.flush()
        last_message = result["messages"][-1]
        print(f"\nCoach: {last_message.content}\n")


if __name__ == "__main__":
    main()
