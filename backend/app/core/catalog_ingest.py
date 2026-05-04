from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from backend.app.models.scpi import Catalog, ScpiCommand

SCPI_PATTERN = re.compile(r"(?<![A-Z0-9_])(?:\*|:)[A-Z][A-Z0-9]*(?::[A-Z][A-Z0-9]*)*(?:\?)?", re.IGNORECASE)


@dataclass
class ExtractionResult:
    command: str
    source_file: str
    page: int


class CatalogIngestor:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.catalog_dir = project_root / "backend" / "catalogs"
        self.catalog_path = self.catalog_dir / "areg_commands.json"

    def ingest_manuals(self, manual_paths: Iterable[Path]) -> dict[str, object]:
        extracted: list[ExtractionResult] = []
        for manual_path in manual_paths:
            extracted.extend(self._extract_from_pdf(manual_path))

        catalog = self._merge_into_catalog(extracted)
        self.catalog_path.write_text(
            json.dumps(catalog.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        workflow_dir = self.catalog_dir / "workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        self._write_verification_queue(catalog, workflow_dir / "verification_queue.csv")

        return {
            "catalog_path": str(self.catalog_path),
            "total_commands": len(catalog.commands),
            "verified_commands": sum(1 for cmd in catalog.commands if cmd.verified),
            "unverified_commands": sum(1 for cmd in catalog.commands if not cmd.verified),
        }

    def _extract_from_pdf(self, pdf_path: Path) -> list[ExtractionResult]:
        reader = PdfReader(str(pdf_path))
        results: list[ExtractionResult] = []

        for page_index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            for match in SCPI_PATTERN.findall(text):
                results.append(
                    ExtractionResult(
                        command=match.upper(),
                        source_file=pdf_path.name,
                        page=page_index + 1,
                    )
                )
        return results

    def _merge_into_catalog(self, extracted: list[ExtractionResult]) -> Catalog:
        existing = self._load_existing_catalog()
        by_command: dict[str, ScpiCommand] = {cmd.command.upper(): cmd for cmd in existing.commands}

        for item in extracted:
            existing_cmd = by_command.get(item.command)
            source_ref = f"{item.source_file}#page={item.page}"
            if existing_cmd:
                if existing_cmd.source:
                    sources = {part.strip() for part in existing_cmd.source.split(",") if part.strip()}
                    if source_ref not in sources:
                        existing_cmd.source = ", ".join(sorted(sources | {source_ref}))
                else:
                    existing_cmd.source = source_ref
                continue

            command_type = "query" if item.command.endswith("?") else "action"
            key = self._to_key(item.command)
            by_command[item.command] = ScpiCommand(
                key=key,
                command=item.command,
                type=command_type,
                description="Extracted from manuals. Needs operator verification.",
                example=item.command,
                verified=False,
                source=source_ref,
                verification_status="extracted",
            )

        merged_commands = sorted(by_command.values(), key=lambda c: c.command)
        return Catalog(
            instrument=existing.instrument,
            version="auto-ingest-0.2",
            generated_on=str(date.today()),
            commands=merged_commands,
        )

    def _load_existing_catalog(self) -> Catalog:
        if self.catalog_path.exists():
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            return Catalog.model_validate(data)

        return Catalog(
            instrument="AREG800A",
            version="bootstrap",
            generated_on=str(date.today()),
            commands=[],
        )

    def _write_verification_queue(self, catalog: Catalog, output_path: Path) -> None:
        with output_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(["command", "type", "verification_status", "source"])
            for command in catalog.commands:
                if not command.verified:
                    writer.writerow([
                        command.command,
                        command.type,
                        command.verification_status,
                        command.source or "",
                    ])

    def _to_key(self, command: str) -> str:
        trimmed = command.strip("?")
        return trimmed.replace("*", "").replace(":", "_").lower()
