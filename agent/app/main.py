"""Entrypoint.

Default mode runs an OFFLINE TEXT SIMULATION of the conversation FSM so you can iterate on scripts
immediately without telephony or API keys. Pass `--live` to run the real Pipecat pipeline (requires
Pipecat installed, API keys set, and a transport wired to ViciDial media).
"""

from __future__ import annotations

import argparse

from loguru import logger

from .config import ScriptConfig
from .conversation import Action, ConversationEngine


def run_simulation() -> None:
    engine = ConversationEngine(script=ScriptConfig.load())
    opening = engine.open()
    print(f"\nBOT: {opening.reply}")
    print("(type the caller's replies; Ctrl-C to quit)\n")

    try:
        while True:
            caller = input("CALLER: ")
            turn = engine.handle(caller)
            print(f"BOT: {turn.reply}")
            if turn.action == Action.TRANSFER:
                print("\n>>> WARM TRANSFER to human closer. Call handed off.\n")
                break
            if turn.action == Action.HANGUP:
                print("\n>>> CALL ENDED (dispositioned).\n")
                break
    except KeyboardInterrupt:
        print("\nbye")


def run_live() -> None:
    logger.info("Live mode requires a transport wired to ViciDial media.")
    logger.info(
        "See app/pipeline.py:build_pipeline — pass a Pipecat transport, then run the PipelineTask "
        "with PipelineRunner. This is the onboarding integration step per BPO."
    )
    raise SystemExit(
        "Live transport not configured in the scaffold. Wire ViciDial/SIP media, then call "
        "build_pipeline(transport, agent_user=...)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI fronter agent")
    parser.add_argument("--live", action="store_true", help="Run the real Pipecat pipeline")
    args = parser.parse_args()
    run_live() if args.live else run_simulation()


if __name__ == "__main__":
    main()
