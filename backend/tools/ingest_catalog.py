from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.catalog_ingest import CatalogIngestor


def main() -> None:
    project_root = PROJECT_ROOT
    manuals = [
        project_root / "Remote_Control_SCPI_GettingStarted_en_04.pdf",
        project_root / "AREG_UserManual_en_08.pdf",
    ]

    ingestor = CatalogIngestor(project_root)
    result = ingestor.ingest_manuals(manuals)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
