"""CLI smoke-test loop for the Money Coach agent.

Usage:
    uv run python -m money_coach.main
"""

from dotenv import load_dotenv

load_dotenv()

from money_coach.graph import graph  # noqa: E402 – must come after load_dotenv
from money_coach.dependencies import get_langfuse_handler, langfuse_client  # noqa: E402


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
