"""Point d'entrée de l'application (utilisé par PyInstaller)."""
import sys

if len(sys.argv) > 1:
    from vidcompare.cli import main
    raise SystemExit(main())

from vidcompare.webapp import run
run()
