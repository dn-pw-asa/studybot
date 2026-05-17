"""Simple WebSocket client for testing studybot with streaming support."""
import asyncio
import json
import sys

from websockets import connect


async def main() -> None:
    uri = "ws://127.0.0.1:8765"
    print(f"Connecting to {uri}...")

    async with connect(uri) as ws:
        print("Connected! Type your messages (or 'quit' to exit).\n")

        async def receiver() -> None:
            current_line = ""
            async for msg in ws:
                data = json.loads(msg)
                event = data.get("event", "")
                content = data.get("content", "")
                done = data.get("done", False)

                if event == "stream":
                    # Streaming: print in place
                    print(content, end="", flush=True)
                    current_line += content
                elif event == "message":
                    # Full message or stream end
                    if current_line and content:
                        print()  # newline after stream
                    if content:
                        print(f"\n📚 Studybot: {content}")
                    current_line = ""
                    print("> ", end="", flush=True)

        task = asyncio.create_task(receiver())

        print("> ", end="", flush=True)
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                line = line.strip()
                if not line:
                    continue
                if line.lower() == "quit":
                    break
                await ws.send(json.dumps({"content": line}))
            except EOFError:
                break

        task.cancel()
        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(main())
