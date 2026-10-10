"""Permite ejecutar `python -m bpt ...` (útil en Windows con Smart App Control,
que puede bloquear el lanzador bpt.exe por no tener firma digital)."""
from bpt.cli import main

raise SystemExit(main())
