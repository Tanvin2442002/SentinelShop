import sys
from pathlib import Path

# Make `import app` resolve to services/catalog-api/app without packaging it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "catalog-api"))
