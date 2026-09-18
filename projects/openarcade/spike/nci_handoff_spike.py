"""NCI Handoff Spike — proves the seamless-launch contract over real UDP loopback.

Instruments every state transition with wall-clock timestamps so a human can
map them to observable failure modes on real hardware:

  - Black-frame gap: time between LAUNCHING → AWAITING_READY (NCI send) and READY
  - Audio-pop: abrupt transition (no fade)
  - Focus-fight: double-transition / state oscillation

Usage:
    python -m spike.nci_handoff_spike          # Default: mock loopback (no hardware)
    python -m spike.nci_handoff_spike --real HOST:PORT  # Real RetroArch (human go/no-go)
"""

from __future__ import annotations

import argparse
import asyncio
import time
import sys


async def run_spike(host: str, port: int, real: bool) -> None:
    from factory.launch.runtime.nci.udp import UdpNciTransport
    from factory.launch.runtime.nci.loopback import LoopbackNciListener
    from factory.launch.runtime.orchestrator import LaunchOrchestrator, LaunchState

    timeline: list[tuple[float, str]] = []
    t0 = time.perf_counter()

    def log(msg: str) -> None:
        elapsed = (time.perf_counter() - t0) * 1000
        timeline.append((elapsed, msg))
        print(f"  [{elapsed:8.2f} ms] {msg}")

    listener: LoopbackNciListener | None = None

    if real:
        print(f"=== REAL MODE: targeting RetroArch at {host}:{port} ===")
        print("⚠️  This is the HUMAN hardware go/no-go. Ensure RetroArch is running with --cmd-port.")
        transport = UdpNciTransport(host=host, port=port)

        # Real mode: no mock readiness — poll forever (timeout controls)
        async def real_probe() -> bool:
            # On real hardware, readiness = first frame rendered.
            # Stub: always False (human observes visually, timeout = failure).
            return False

        probe = real_probe
    else:
        print("=== MOCK MODE: UDP loopback (no hardware required) ===")
        listener = LoopbackNciListener()
        bound_port = await listener.start()
        log(f"Loopback listener bound on 127.0.0.1:{bound_port}")

        transport = UdpNciTransport(host="127.0.0.1", port=bound_port)

        # Signal readiness after a short delay (simulates RetroArch rendering first frame)
        async def delayed_ready() -> None:
            await asyncio.sleep(0.05)
            listener.signal_ready()  # type: ignore[union-attr]
            log("Readiness signal fired (simulated first-frame)")

        asyncio.get_running_loop().create_task(delayed_ready())
        probe = listener.readiness_probe

    log(f"Transport: UdpNciTransport -> {host}:{port if real else listener.bound_port}")  # type: ignore[union-attr]

    orch = LaunchOrchestrator(
        transport=transport,
        readiness_probe=probe,
        poll_interval=0.01,
        timeout=2.0 if real else 1.0,
    )

    log(f"State: {orch.state.name}")

    # Execute launch
    log(">>> Launching: LOAD_CORE + LOAD_CONTENT")
    result = await orch.launch(
        content_path="/roms/kinst.zip",
        core="/usr/lib/libretro/mame_libretro.so",
    )
    log(f"State: {result.name}")

    if result == LaunchState.READY:
        log("✅ HANDOFF SUCCESS — orchestrator reached READY")
    else:
        log("❌ HANDOFF FAILED — timeout waiting for readiness")

    # Quit
    await orch.quit()
    log(f"State: {orch.state.name} (after QUIT)")

    # Report what the listener saw (mock mode only)
    if listener:
        log(f"Listener received {len(listener.received)} datagrams:")
        for i, data in enumerate(listener.received):
            log(f"  [{i}] {data!r}")
        await listener.stop()

    await transport.close()

    # Summary
    print("\n=== INSTRUMENTED TIMELINE ===")
    for elapsed, msg in timeline:
        print(f"  [{elapsed:8.2f} ms] {msg}")

    total = timeline[-1][0] if timeline else 0
    print(f"\n  Total handoff time: {total:.2f} ms")
    if not real:
        print("  (Mock mode — real-hardware latency will differ)")
        print("  Human go/no-go: run with --real HOST:PORT against live RetroArch")


def main() -> None:
    parser = argparse.ArgumentParser(description="NCI Handoff Spike")
    parser.add_argument(
        "--real",
        metavar="HOST:PORT",
        help="Target a real RetroArch instance (e.g. 192.168.1.50:55355). "
        "Default: mock loopback on ephemeral port.",
    )
    args = parser.parse_args()

    if args.real:
        parts = args.real.rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 55355
        asyncio.run(run_spike(host, port, real=True))
    else:
        asyncio.run(run_spike("127.0.0.1", 0, real=False))


if __name__ == "__main__":
    main()
