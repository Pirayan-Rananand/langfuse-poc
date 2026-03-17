"""Factories for nonprod and prod Langfuse clients.

Nonprod client: uses LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY (dev/sit traces + dataset).
Prod client: uses LANGFUSE_PROD_SECRET_KEY / LANGFUSE_PROD_PUBLIC_KEY (prompt versions).
"""

import os

from langfuse import Langfuse


def make_nonprod_client() -> Langfuse:
    return Langfuse(
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )


def make_prod_client() -> Langfuse:
    return Langfuse(
        secret_key=os.environ["LANGFUSE_PROD_SECRET_KEY"],
        public_key=os.environ["LANGFUSE_PROD_PUBLIC_KEY"],
        host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
