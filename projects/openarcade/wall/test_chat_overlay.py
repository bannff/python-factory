"""Tests for the assistant-anywhere bead: AssistantVM, chat overlay, root Stack."""

from unittest.mock import MagicMock, patch
import flet as ft

from wall.assistant_vm import AssistantVM
from wall.assistant_panel import ChatMessage
from wall.chat_overlay import build_chat_overlay
from wall.models import GameTile, WallViewModel
from wall.navigator import Navigator


def _tile(title="Test", system="SNES"):
    return GameTile(
        id=f"{system}-{title}", title=title, system=system,
        art_url="", rom_path="", core=None, playable=True,
    )


def _vm():
    return WallViewModel(tiles=[_tile("A"), _tile("B")], columns=2)


def _make_nav():
    """Build a Navigator with mocked assistant deps.

    _reload_assistant does lazy imports from control_plane which isn't on the
    test path, so we patch the method directly on the class.
    """
    with patch.object(Navigator, "_reload_assistant", lambda self: None):
        nav = Navigator(_vm())
    # Set sensible defaults on the VM since _reload_assistant was skipped
    nav._assistant_vm.is_null = True
    nav._assistant_vm._assistant = MagicMock()
    return nav


# --- AssistantVM ---

def test_assistant_vm_messages_shared():
    """VM messages list is a single shared instance."""
    vm = AssistantVM()
    vm.messages.append(ChatMessage(role="user", text="hello"))
    assert len(vm.messages) == 1
    assert vm.messages[0].text == "hello"


def test_assistant_vm_reload_calls_fn():
    """reload_config delegates to the registered function."""
    called = []
    vm = AssistantVM()
    vm._reload_fn = lambda: called.append(True)
    vm.reload_config()
    assert called == [True]


# --- Navigator exposes assistant_vm ---

def test_navigator_has_assistant_vm_property():
    """Navigator exposes the AssistantVM via .assistant_vm property."""
    nav = _make_nav()
    assert isinstance(nav.assistant_vm, AssistantVM)
    assert nav.assistant_vm is nav._assistant_vm


def test_navigator_backward_compat_messages():
    """Backward-compat _assistant_messages accessor returns VM.messages."""
    nav = _make_nav()
    nav.assistant_vm.messages.append(ChatMessage(role="user", text="hi"))
    assert nav._assistant_messages is nav.assistant_vm.messages
    assert len(nav._assistant_messages) == 1


# --- Chat overlay ---

def test_build_chat_overlay_returns_drawer_and_fab():
    """build_chat_overlay returns (drawer, fab) containers."""
    nav = _make_nav()
    drawer, fab = build_chat_overlay(nav, nav.assistant_vm)
    assert isinstance(drawer, ft.Container)
    assert isinstance(fab, ft.Container)


def test_fab_toggles_drawer_offset():
    """FAB toggle flips drawer offset between hidden and visible."""
    nav = _make_nav()
    drawer, fab = build_chat_overlay(nav, nav.assistant_vm)
    # Initially hidden (offset.x == 1.0)
    assert drawer.offset.x == 1.0
    assert not drawer.is_open()
    # Toggle open
    drawer.toggle()
    assert drawer.offset.x == 0
    assert drawer.is_open()
    # Toggle closed
    drawer.toggle()
    assert drawer.offset.x == 1.0
    assert not drawer.is_open()


def test_drawer_and_landing_share_same_vm_instance():
    """The drawer and landing page share the SAME AssistantVM (identity)."""
    nav = _make_nav()
    vm = nav.assistant_vm
    drawer, fab = build_chat_overlay(nav, vm)
    # Add a message via the VM (simulates drawer send)
    vm.messages.append(ChatMessage(role="user", text="from drawer"))
    # Navigator's backward-compat property sees the same message
    assert nav._assistant_messages[-1].text == "from drawer"
    # Same object identity
    assert nav._assistant_messages is vm.messages


# --- App root Stack structure ---

def test_app_target_creates_stack_root():
    """After _target runs, page has an outer vibrant-bg Stack of 3 layers:
    gradient, aura, and the content stack (nav Row, drawer, fab).

    Structure changed under bead python-factory-3c388 (Arcade motion +
    vibrant theme, meta-architect APPROVED): the page root is now a layered
    Stack with a radial-gradient background layer and a per-system aura tint
    layer beneath the existing content stack, so the vibrant background
    renders under the nav/drawer/fab without altering their own layout.
    """
    with patch("wall.app._build_vm") as mock_build, \
         patch.object(Navigator, "_reload_assistant", lambda self: None):
        mock_build.return_value = (_vm(), None)

        from wall.app import _target
        page = MagicMock(spec=ft.Page)
        page.web = True
        page.controls = []

        def _add(ctrl):
            page.controls.append(ctrl)

        page.add = _add
        _target(page)

    assert len(page.controls) == 1
    root = page.controls[0]
    assert isinstance(root, ft.Stack)
    assert root.expand is True
    # 3 layers: gradient background, aura tint, content stack (nav/drawer/fab)
    assert len(root.controls) == 3
    gradient_layer, aura_layer, content_stack = root.controls
    assert isinstance(gradient_layer, ft.Container)
    assert isinstance(gradient_layer.gradient, ft.RadialGradient)
    assert isinstance(aura_layer, ft.Container)
    assert isinstance(content_stack, ft.Stack)
    assert len(content_stack.controls) == 3
    assert isinstance(content_stack.controls[0], ft.Row)  # nav
    assert isinstance(content_stack.controls[1], ft.Container)  # drawer
    assert isinstance(content_stack.controls[2], ft.Container)  # fab


# --- Drawer wide mode (bead k9mmu: resizable assistant) ---


def test_drawer_wide_mode_toggle():
    """toggle_wide switches drawer width between 400 and 640."""
    from wall.chat_overlay import _DRAWER_WIDTH, _DRAWER_WIDE

    nav = _make_nav()
    drawer, fab = build_chat_overlay(nav, nav.assistant_vm)
    # Default narrow
    assert drawer.width == _DRAWER_WIDTH
    assert not drawer.is_wide()
    # Toggle wide
    drawer.toggle_wide()
    assert drawer.width == _DRAWER_WIDE
    assert drawer.is_wide()
    # Toggle back to narrow
    drawer.toggle_wide()
    assert drawer.width == _DRAWER_WIDTH
    assert not drawer.is_wide()


def test_drawer_width_clamped_to_known_values():
    """Width only ever takes one of two values -- no arbitrary resize."""
    from wall.chat_overlay import _DRAWER_WIDTH, _DRAWER_WIDE

    nav = _make_nav()
    drawer, fab = build_chat_overlay(nav, nav.assistant_vm)
    # Multiple toggles stay bounded
    for _ in range(5):
        drawer.toggle_wide()
    assert drawer.width in (_DRAWER_WIDTH, _DRAWER_WIDE)
