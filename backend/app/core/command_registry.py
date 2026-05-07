from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.areg_controller import CommandSource
from backend.app.core.catalog import load_catalog
from backend.app.core.config import load_settings


PLACEHOLDER_PATTERN = re.compile(r"<([^>]+)>")


@dataclass(frozen=True)
class RegistryCommand:
    key: str
    group: str
    command: str
    command_type: str
    purpose: str
    example: str | None = None
    placeholders: tuple[str, ...] = ()
    source: str | None = None
    verified: bool = False
    origin: str = "builtin"
    expected_response: bool | None = None
    timeout_ms: int | None = None
    parser: str | None = None


class CommandRegistryService:
    """Unified command registry for the manual console and scenario controls."""

    def __init__(self, command_source_path: Path | None = None) -> None:
        settings = load_settings()
        self.command_source_path = command_source_path or settings.command_source_path

    def _extract_placeholders(self, command: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(match.strip() for match in PLACEHOLDER_PATTERN.findall(command)))

    def _builtin_commands(self) -> list[RegistryCommand]:
        commands = [
            RegistryCommand(
                key="core.idn",
                group="Core",
                command="*IDN?",
                command_type="query",
                purpose="Identify the connected instrument.",
                example="*IDN?",
                verified=True,
            ),
            RegistryCommand(
                key="core.clear_status",
                group="Core",
                command="*CLS",
                command_type="action",
                purpose="Clear status registers and error queue.",
                example="*CLS",
                verified=True,
            ),
            RegistryCommand(
                key="core.opc_query",
                group="Core",
                command="*OPC?",
                command_type="query",
                purpose="Wait for operation complete.",
                example="*OPC?",
                verified=True,
            ),
            RegistryCommand(
                key="system.error_all",
                group="Diagnostics",
                command="SYSTem:ERRor:ALL?",
                command_type="query",
                purpose="Read the instrument error queue.",
                example="SYSTem:ERRor:ALL?",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.language",
                group="Hardcopy",
                command=":HCOPy:DEVice:LANGuage <file_format>",
                command_type="write",
                purpose="Select the hardcopy image format.",
                example=":HCOPy:DEVice:LANGuage PNG",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.auto_name",
                group="Hardcopy",
                command=":HCOPy:FILE:NAME:AUTO:STATe <state>",
                command_type="write",
                purpose="Enable or disable instrument-managed hardcopy file naming.",
                example=":HCOPy:FILE:NAME:AUTO:STATe 1",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.execute",
                group="Hardcopy",
                command=":HCOPy:EXECute",
                command_type="action",
                purpose="Trigger hardcopy generation on the instrument.",
                example=":HCOPy:EXECute",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.data",
                group="Hardcopy",
                command=":HCOPy:DATA?",
                command_type="binary-query",
                purpose="Read hardcopy data as a definite-length SCPI binary block.",
                example=":HCOPy:DATA?",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.catalog",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:FILE:CATalog?",
                command_type="query",
                purpose="List available .osi and .sm scenario files in default directory (/var/user).",
                example="SOURce1:AREGenerator:SCENario:FILE:CATalog?",
                verified=True,
                expected_response=True,
                parser="scenario_catalog",
            ),
            RegistryCommand(
                key="scenario.file",
                group="Scenario Player",
                command='SOURce<source_hw>:AREGenerator:SCENario:FILE "<scenario_name>"',
                command_type="write",
                purpose="Load a scenario file by absolute path.",
                example='SOURce1:AREGenerator:SCENario:FILE "/var/user/myScenario.osi"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.play",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STARt",
                command_type="action",
                purpose="Start playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:STARt",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.pause",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:PAUSe",
                command_type="action",
                purpose="Pause playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:PAUSe",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.stop",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STOP",
                command_type="action",
                purpose="Stop playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:STOP",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.reset",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:RESet",
                command_type="action",
                purpose="Reset playback state/position for the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:RESet",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.status",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STATus?",
                command_type="query",
                purpose="Query scenario playback status.",
                example="SOURce1:AREGenerator:SCENario:STATus?",
                verified=True,
                expected_response=True,
                parser="string",
            ),
            RegistryCommand(
                key="scenario.progress",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:PROGress?",
                command_type="query",
                purpose="Query scenario playback progress.",
                example="SOURce1:AREGenerator:SCENario:PROGress?",
                verified=True,
                expected_response=True,
                parser="number",
            ),
            RegistryCommand(
                key="scenario.position.actual",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:POSition:ACTual?",
                command_type="query",
                purpose="Query actual scenario position.",
                example="SOURce1:AREGenerator:SCENario:POSition:ACTual?",
                verified=True,
                expected_response=True,
                parser="integer",
            ),
            RegistryCommand(
                key="scenario.position.start",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:POSition:STARt <value>",
                command_type="write",
                purpose="Set scenario start position.",
                example="SOURce1:AREGenerator:SCENario:POSition:STARt 0",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.position.stop",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:POSition:STOP <value>",
                command_type="write",
                purpose="Set scenario stop position.",
                example="SOURce1:AREGenerator:SCENario:POSition:STOP 100",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.replay_mode.set",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:REPLay:MODE <mode>",
                command_type="write",
                purpose="Set replay mode to SINGle or LOOP.",
                example="SOURce1:AREGenerator:SCENario:REPLay:MODE LOOP",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="scenario.replay_mode.query",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:REPLay:MODE?",
                command_type="query",
                purpose="Query the current replay mode.",
                example="SOURce1:AREGenerator:SCENario:REPLay:MODE?",
                verified=True,
                expected_response=True,
                parser="string",
            ),
            RegistryCommand(
                key="scenario.state",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STATe?",
                command_type="action",
                purpose="Trigger scenario state handling on instrument (no response expected).",
                example="SOURce1:AREGenerator:SCENario:STATe?",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.cdir.query",
                group="Memory Manager",
                command="MMEMory:CDIRectory?",
                command_type="query",
                purpose="Query default memory directory.",
                example="MMEMory:CDIRectory?",
                verified=True,
                expected_response=True,
                parser="string",
            ),
            RegistryCommand(
                key="memory.cdir.set",
                group="Memory Manager",
                command='MMEMory:CDIRectory "<path>"',
                command_type="write",
                purpose="Set default memory directory.",
                example='MMEMory:CDIRectory "/var/user"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.catalog",
                group="Memory Manager",
                command='MMEMory:CATalog? "<path>"',
                command_type="query",
                purpose="List files in memory directory.",
                example='MMEMory:CATalog? "/var/user"',
                verified=True,
                expected_response=True,
                parser="memory_catalog",
            ),
            RegistryCommand(
                key="memory.dcatalog",
                group="Memory Manager",
                command='MMEMory:DCATalog? "<path>"',
                command_type="query",
                purpose="List subdirectories in memory directory.",
                example='MMEMory:DCATalog? "/var/user"',
                verified=True,
                expected_response=True,
                parser="memory_dcatalog",
            ),
            RegistryCommand(
                key="memory.catalog.length",
                group="Memory Manager",
                command='MMEMory:CATalog:LENGth? "<path>"',
                command_type="query",
                purpose="Count files in directory.",
                example='MMEMory:CATalog:LENGth? "/var/user"',
                verified=True,
                expected_response=True,
                parser="integer",
            ),
            RegistryCommand(
                key="memory.dcatalog.length",
                group="Memory Manager",
                command='MMEMory:DCATalog:LENGth? "<path>"',
                command_type="query",
                purpose="Count subdirectories in directory.",
                example='MMEMory:DCATalog:LENGth? "/var/user"',
                verified=True,
                expected_response=True,
                parser="integer",
            ),
            RegistryCommand(
                key="memory.mkdir",
                group="Memory Manager",
                command='MMEMory:MDIRectory "<path>"',
                command_type="write",
                purpose="Create directory.",
                example='MMEMory:MDIRectory "/var/user/new"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.copy",
                group="Memory Manager",
                command='MMEMory:COPY "<src>","<dst>"',
                command_type="write",
                purpose="Copy file.",
                example='MMEMory:COPY "/var/user/a.osi","/var/user/new/a.osi"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.move",
                group="Memory Manager",
                command='MMEMory:MOVE "<src>","<dst>"',
                command_type="write",
                purpose="Move or rename file.",
                example='MMEMory:MOVE "settings.savrcltxt","settings_new.savrcltxt"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.rdir",
                group="Memory Manager",
                command='MMEMory:RDIRectory "<path>"',
                command_type="write",
                purpose="Delete empty directory.",
                example='MMEMory:RDIRectory "/var/user/test"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="memory.rdir.recursive",
                group="Memory Manager",
                command='MMEMory:RDIRectory:RECursive "<path>"',
                command_type="write",
                purpose="Delete directory recursively.",
                example='MMEMory:RDIRectory:RECursive "/var/user/test"',
                verified=True,
                expected_response=False,
            ),
            # ----------------------------------------------------------------
            # HCOPy subsystem (R&S AREG800A User Manual)
            # ----------------------------------------------------------------
            RegistryCommand(
                key="hcopy.format",
                group="HCOPy",
                command=":HCOPy:DEVice:LANGuage <format>",
                command_type="write",
                purpose="Set hardcopy image format. Allowed: PNG, BMP, JPG, XPM.",
                example=":HCOPy:DEVice:LANGuage PNG",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.format.alt",
                group="HCOPy",
                command=":HCOPy:IMAGe:FORMat <format>",
                command_type="write",
                purpose="Alternative command to set hardcopy image format (prefer hcopy.format).",
                example=":HCOPy:IMAGe:FORMat PNG",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.region",
                group="HCOPy",
                command=":HCOPy:REGion <region>",
                command_type="write",
                purpose="Set hardcopy region. Allowed: ALL (whole screen), DIALog (active dialog).",
                example=":HCOPy:REGion ALL",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.filename",
                group="HCOPy",
                command=':HCOPy:FILE:NAME "<path>"',
                command_type="write",
                purpose="Set explicit filename for hardcopy (used when automatic naming is disabled).",
                example=':HCOPy:FILE:NAME "/var/user/hardcopy_test.png"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.execute",
                group="HCOPy",
                command=":HCOPy:EXECute",
                command_type="action",
                purpose="Execute hardcopy – saves screenshot to the instrument file system. Event command; no response.",
                example=":HCOPy:EXECute",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.data",
                group="HCOPy",
                command=":HCOPy:DATA?",
                command_type="query",
                purpose="Transfer hardcopy image binary data directly to PC (NByte/block-data stream).",
                example=":HCOPy:DATA?",
                verified=True,
                expected_response=True,
                parser="binary_block",
            ),
            RegistryCommand(
                key="hcopy.auto.state",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:STATe <state>",
                command_type="write",
                purpose="Enable (1) or disable (0) automatic filename generation.",
                example=":HCOPy:FILE:NAME:AUTO:STATe 1",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.query",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO?",
                command_type="query",
                purpose="Query the full path of the automatically generated hardcopy file.",
                example=":HCOPy:FILE:NAME:AUTO?",
                verified=True,
                expected_response=True,
                parser="string",
            ),
            RegistryCommand(
                key="hcopy.auto.directory",
                group="HCOPy",
                command=':HCOPy:FILE:NAME:AUTO:DIRectory "<directory>"',
                command_type="write",
                purpose="Set the directory used for automatic hardcopy file naming.",
                example=':HCOPy:FILE:NAME:AUTO:DIRectory "/var/user/HCopy"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.directory.clear",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:DIRectory:CLEar",
                command_type="action",
                purpose="Delete all .bmp/.jpg/.png/.xpm files from the automatic naming directory. DANGEROUS – requires confirmation.",
                example=":HCOPy:FILE:NAME:AUTO:DIRectory:CLEar",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.file.query",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE?",
                command_type="query",
                purpose="Query the auto-generated filename (without path).",
                example=":HCOPy:FILE:NAME:AUTO:FILE?",
                verified=True,
                expected_response=True,
                parser="string",
            ),
            RegistryCommand(
                key="hcopy.auto.number.query",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE:NUMBer?",
                command_type="query",
                purpose="Query the number component used in the next automatic hardcopy filename.",
                example=":HCOPy:FILE:NAME:AUTO:FILE:NUMBer?",
                verified=True,
                expected_response=True,
                parser="integer",
            ),
            RegistryCommand(
                key="hcopy.auto.prefix.state",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE:PREFix:STATe <state>",
                command_type="write",
                purpose="Enable (1) or disable (0) the prefix component in automatic naming.",
                example=":HCOPy:FILE:NAME:AUTO:FILE:PREFix:STATe 1",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.prefix",
                group="HCOPy",
                command=':HCOPy:FILE:NAME:AUTO:FILE:PREFix "<prefix>"',
                command_type="write",
                purpose="Set the prefix string used in automatic hardcopy filenames.",
                example=':HCOPy:FILE:NAME:AUTO:FILE:PREFix "hardcopy"',
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.year.state",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE:YEAR:STATe <state>",
                command_type="write",
                purpose="Enable (1) or disable (0) the year component in automatic hardcopy filenames.",
                example=":HCOPy:FILE:NAME:AUTO:FILE:YEAR:STATe 1",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.month.state",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE:MONTh:STATe <state>",
                command_type="write",
                purpose="Enable (1) or disable (0) the month component in automatic hardcopy filenames.",
                example=":HCOPy:FILE:NAME:AUTO:FILE:MONTh:STATe 1",
                verified=True,
                expected_response=False,
            ),
            RegistryCommand(
                key="hcopy.auto.day.state",
                group="HCOPy",
                command=":HCOPy:FILE:NAME:AUTO:FILE:DAY:STATe <state>",
                command_type="write",
                purpose="Enable (1) or disable (0) the day component in automatic hardcopy filenames.",
                example=":HCOPy:FILE:NAME:AUTO:FILE:DAY:STATe 1",
                verified=True,
                expected_response=False,
            ),
        ]
        return [
            RegistryCommand(
                **{
                    **command.__dict__,
                    "placeholders": self._extract_placeholders(command.command),
                }
            )
            for command in commands
        ]

    def _yaml_commands(self) -> tuple[list[RegistryCommand], str | None]:
        if not self.command_source_path.exists():
            return [], f"Optional command source not found: {self.command_source_path.name}. Using built-in registry and catalog fallback."

        try:
            source = CommandSource.load(self.command_source_path).document
        except Exception as ex:
            return [], f"Failed to read optional command source: {ex}. Using built-in registry and catalog fallback."

        command_groups = source.get("command_groups", {})
        if not isinstance(command_groups, dict):
            return [], "Optional command source is malformed. Using built-in registry and catalog fallback."

        commands: list[RegistryCommand] = []
        for group_name, group_data in command_groups.items():
            if not isinstance(group_data, dict):
                continue
            commands_list = group_data.get("commands", [])
            if not isinstance(commands_list, list):
                continue
            for index, command_item in enumerate(commands_list):
                if not isinstance(command_item, dict):
                    continue
                command_text = str(command_item.get("command", "")).strip()
                if not command_text:
                    continue
                entry_key = str(command_item.get("key") or f"yaml.{group_name}.{index}")
                commands.append(
                    RegistryCommand(
                        key=entry_key,
                        group=str(group_name),
                        command=command_text,
                        command_type="query" if command_text.split()[0].endswith("?") else "write",
                        purpose=str(command_item.get("purpose", "")),
                        example=command_item.get("example"),
                        placeholders=self._extract_placeholders(command_text),
                        source=str(self.command_source_path),
                        verified=False,
                        origin="yaml",
                    )
                )
        return commands, None

    def _catalog_commands(self) -> list[RegistryCommand]:
        catalog = load_catalog()
        commands: list[RegistryCommand] = []
        for entry in catalog.commands:
            commands.append(
                RegistryCommand(
                    key=f"catalog.{entry.key}.{len(commands)}",
                    group="Catalog",
                    command=entry.command,
                    command_type=entry.type,
                    purpose=entry.description,
                    example=entry.example,
                    placeholders=self._extract_placeholders(entry.command),
                    source=entry.source,
                    verified=entry.verified,
                    origin="catalog",
                )
            )
        return commands

    def list_commands(self) -> tuple[list[RegistryCommand], str]:
        warning_parts: list[str] = []
        commands_by_command: dict[str, RegistryCommand] = {}
        commands_by_key: dict[str, RegistryCommand] = {}

        def add(entry: RegistryCommand) -> None:
            normalized_command = entry.command.strip().upper()
            if entry.key not in commands_by_key:
                commands_by_key[entry.key] = entry
            if normalized_command not in commands_by_command:
                commands_by_command[normalized_command] = entry

        for entry in self._builtin_commands():
            add(entry)

        yaml_commands, yaml_warning = self._yaml_commands()
        if yaml_warning:
            warning_parts.append(yaml_warning)
        for entry in yaml_commands:
            add(entry)

        for entry in self._catalog_commands():
            add(entry)

        commands = sorted(commands_by_command.values(), key=lambda item: (item.group, item.command))
        return commands, " ".join(warning_parts).strip()

    def command_library(self) -> dict[str, Any]:
        commands, warning = self.list_commands()
        placeholder_help = {
            "source_hw": "Source hardware index",
            "directory": "Remote directory path",
            "scenario_name": "Remote scenario filename or path",
            "mode": "Replay mode, e.g. SINGle or LOOP",
            "file_format": "Hardcopy format such as PNG/JPG/BMP",
            "state": "Boolean state, typically 0/1 or ON/OFF",
        }
        return {
            "device": "AREG800A",
            "warning": warning,
            "placeholders": placeholder_help,
            "commands": [
                {
                    "key": entry.key,
                    "group": entry.group,
                    "command": entry.command,
                    "purpose": entry.purpose,
                    "example": entry.example,
                    "placeholders": list(entry.placeholders),
                    "command_type": entry.command_type,
                    "verified": entry.verified,
                    "origin": entry.origin,
                    "source": entry.source,
                    "expected_response": entry.expected_response,
                    "timeout_ms": entry.timeout_ms,
                    "parser": entry.parser,
                }
                for entry in commands
            ],
        }

    def resolve(self, key: str, values: dict[str, object] | None = None) -> str:
        values = values or {}
        commands, _warning = self.list_commands()
        entry = next((command for command in commands if command.key == key), None)
        if entry is None:
            raise KeyError(f"Unknown command key: {key}")

        def replace(match: re.Match[str]) -> str:
            name = match.group(1).strip()
            if name not in values:
                raise KeyError(f"Missing placeholder '{name}' for command key '{key}'")
            return str(values[name])

        return PLACEHOLDER_PATTERN.sub(replace, entry.command)

    def lookup(self, command_line: str) -> dict[str, Any]:
        cleaned = command_line.strip()
        if not cleaned:
            return {"known": False, "matches": []}
        normalized = cleaned.upper()
        commands, _warning = self.list_commands()
        matches = [
            {
                "key": entry.key,
                "command": entry.command,
                "group": entry.group,
                "command_type": entry.command_type,
                "purpose": entry.purpose,
                "verified": entry.verified,
                "origin": entry.origin,
            }
            for entry in commands
            if normalized.startswith(entry.command.upper().split()[0])
        ]
        return {"known": bool(matches), "matches": matches[:10]}