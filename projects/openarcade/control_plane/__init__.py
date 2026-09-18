"""OpenArcade MCP Control Plane — agent-drivable surface over the library + settings.

Per-capability modules:
  library_tools   — list, search, get games
  launch_tools    — launch a game via RetroArch
  settings_tools  — get/set global settings, get_controls, set_runahead
  systems_tools   — list available systems

Pure shared core:
  settings_query  — resolve_core, get_global_settings, list_systems
  serializers     — tile_summary, tile_detail
  context         — ServerContext dataclass
"""
