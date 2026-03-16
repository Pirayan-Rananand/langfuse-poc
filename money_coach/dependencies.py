from langfuse import get_client
from langfuse.langchain import CallbackHandler

# Singleton client — use for manual spans, scoring, and flush/shutdown calls.
langfuse_client = get_client()


def get_langfuse_handler() -> CallbackHandler:
    # To attach a session_id, pass ``metadata={"langfuse_session_id": <id>}``
    # in the LangChain run config — the handler reads it from there.

    return CallbackHandler()
