"""Runnable Flet game-wall window. Phase-2 B14."""

import os
import tempfile
from pathlib import Path

import flet as ft

from .curator_bridge import wall_from_scan
from .fixtures import create_fixture_tree
from .gamelist_source import load_gamelist
from .models import WallViewModel
from .navigator import Navigator
from .retroarch_config import RetroArchConfig
from .launch_handler import LaunchHandler
from .chat_overlay import build_chat_overlay
from . import components as C
from . import theme as T


def _build_vm() -> tuple[WallViewModel, str | None]:
    """Build the wall VM. Returns (vm, assets_dir_or_None)."""
    gl_path = os.environ.get("OPENARCADE_GAMELIST")
    media_root = os.environ.get("OPENARCADE_MEDIA_ROOT")
    if gl_path and media_root:
        gl = Path(gl_path)
        system = os.environ.get("OPENARCADE_SYSTEM") or gl.parent.name
        media_root_path = Path(media_root)
        # Derive roms_root: explicit env or RetroPie convention (media_root/<system>)
        roms_root_env = os.environ.get("OPENARCADE_ROMS_ROOT")
        roms_root = Path(roms_root_env) if roms_root_env else media_root_path / system.lower()
        tiles = load_gamelist(gl, system=system, media_root=media_root_path, roms_root=roms_root)
        return WallViewModel(tiles=tiles, columns=3), media_root
    rom, cores, bios = create_fixture_tree(Path(tempfile.mkdtemp(prefix="openarcade_")))
    return wall_from_scan(rom, cores, bios), None


def _target(page: ft.Page) -> None:
    page.title = "OpenArcade"
    page.bgcolor = T.BG_BASE
    page.padding = 0  # rail bleeds flush to the window edge (kiosk look); body carries its own padding
    if not page.web:
        page.window.width = 1440
        page.window.height = 900
        page.window.min_width = 960
        page.window.min_height = 600
        page.window.maximized = True
    vm, assets_dir = _build_vm()
    config_dir = Path(os.environ.get("OPENARCADE_CONFIG_DIR", "./openarcade_config"))

    # Build RetroArchConfig if media_root is available
    media_root_str = os.environ.get("OPENARCADE_MEDIA_ROOT")
    ra_config: RetroArchConfig | None = None
    media_root_path: Path | None = None
    if media_root_str:
        media_root_path = Path(media_root_str)
        ra_config = RetroArchConfig(media_root=media_root_path, config_dir=config_dir)

    # Build LaunchHandler (needs core resolution from ra_config)
    launch_handler: LaunchHandler | None = None
    if ra_config:
        launch_handler = LaunchHandler(resolve_core=ra_config.resolve_core_for_game, page=page)

    nav = Navigator(
        vm, page,
        config_dir=config_dir,
        media_root=media_root_path,
        retroarch_config=ra_config,
        launch_handler=launch_handler,
    )

    # Root Stack: nav fills the view; drawer + FAB overlay on top.
    chat_drawer, chat_fab = build_chat_overlay(nav, nav.assistant_vm)
    content_stack = ft.Stack(
        expand=True,
        controls=[nav.control, chat_drawer, chat_fab],
    )

    # Vibrant background: radial gradient "glow from below" base layer, plus a
    # per-system accent aura tint that fades in when a system filter is active.
    # Layered UNDER the content stack so nav/drawer/tiles render normally on top.
    gradient_layer = ft.Container(
        expand=True,
        gradient=ft.RadialGradient(
            center=ft.Alignment.BOTTOM_CENTER,
            radius=1.4,
            colors=[T.GRADIENT_CORE, T.BG_BASE],
            stops=[0.0, 1.0],
        ),
    )
    aura_layer = ft.Container(
        expand=True,
        bgcolor=C.system_accent(nav.library.active_system),
        opacity=T.AURA_OPACITY_ACTIVE if nav.library.active_system else 0,
        animate_opacity=ft.Animation(T.duration(T.DURATION_SLOW), T.CURVE_STANDARD),
    )
    root_stack = ft.Stack(
        expand=True,
        controls=[gradient_layer, aura_layer, content_stack],
    )
    page.add(root_stack)


def _assets_dir() -> str | None:
    return os.environ.get("OPENARCADE_MEDIA_ROOT")


def run(view: ft.AppView = ft.AppView.FLET_APP) -> None:
    """Launch the native desktop window."""
    kwargs: dict = {"view": view}
    ad = _assets_dir()
    if ad:
        kwargs["assets_dir"] = ad
    ft.run(_target, **kwargs)


def run_web(*, host: str = "127.0.0.1", port: int = 8550, open_browser: bool = False) -> None:
    """Serve the SAME UI as a localhost web page, for visual self-verification.

    Bound to 127.0.0.1 only. Flet 0.85 only serves via the WEB_BROWSER view
    (view=None does not start a server), so the server always uses it; a browser
    tab may open on the host desktop, which is harmless for a localhost loop.
    """
    kwargs: dict = {"view": ft.AppView.WEB_BROWSER, "host": host, "port": port}
    ad = _assets_dir()
    if ad:
        kwargs["assets_dir"] = ad
    ft.run(_target, **kwargs)


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if "web" in args:
        port = int(os.environ.get("OPENARCADE_WEB_PORT", "8550"))
        run_web(port=port, open_browser="--open" in args)
    else:
        run()
