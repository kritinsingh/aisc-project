"""PathPilot - Robot Path Planning Simulator.

Run with:   python main.py
"""
import asyncio

from sim.app import App


async def main():
    app = App()
    await app.run_loop()


asyncio.run(main())
