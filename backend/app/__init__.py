"""CoachLink backend application package.

Note for tooling: this file (and the ``__init__.py`` of each sub-package) is not
decorative. Without it, ``mypy app/domain`` resolves the files as top-level
modules ``ids`` / ``enums``, so the ``[[tool.mypy.overrides]] module =
"app.domain.*"`` strict section never matches and silently does nothing.
"""

__version__ = "0.1.0"
