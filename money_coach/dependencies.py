"""Shared dependencies — Langfuse tracing setup.

Provides a CallbackHandler for automatic LangChain/LangGraph instrumentation
and a singleton client for manual spans, scoring, and flushing.

Usage
-----
Pass ``get_langfuse_handler()`` in the LangChain ``config`` when invoking the
graph so tracing is captured end-to-end:

    from money_coach.dependencies import get_langfuse_handler, langfuse_client

    handler = get_langfuse_handler()
    graph.invoke(state, config={"callbacks": [handler]})
    langfuse_client.flush()  # ensure events are sent before process exits

Environment variables (all optional — handler is a no-op when absent):

    LANGFUSE_SECRET_KEY   sk-lf-...
    LANGFUSE_PUBLIC_KEY   pk-lf-...
    LANGFUSE_HOST         https://cloud.langfuse.com  (default)
"""

from langfuse import get_client
from langfuse.langchain import CallbackHandler

# Singleton client — use for manual spans, scoring, and flush/shutdown calls.
langfuse_client = get_client()


def get_langfuse_handler() -> CallbackHandler:
    """Return a fresh Langfuse CallbackHandler for one graph invocation.

    A new instance per invocation keeps ``last_trace_id`` request-scoped and
    avoids cross-request state leakage in concurrent environments.

    The handler is a no-op when ``LANGFUSE_SECRET_KEY`` is not set, so the
    app runs safely without Langfuse credentials.
    """
    return CallbackHandler()
