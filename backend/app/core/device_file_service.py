"""Device file service - scan and upload OSI files on the connected AREG instrument.

Provides:
- scan_device_osi_files(directory) -> list[DeviceOsiFile]
  Queries the device file system via SCPI and returns .osi files only.

- upload_osi_file(local_path, remote_path) -> UploadResult
  Validates the local file and transfers it to the device via SCPI MMEMory:DATA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.core.scpi_service import ScpiService
from backend.app.core.hislip import ScpiTransportError


# Default scan base when no directory is supplied.
DEFAULT_SCAN_DIRECTORY = "/"

# Common storage locations found on instruments. SD-like paths are included
# so mounted cards can be discovered even when not visible under /osi.
FALLBACK_OSI_DIRECTORIES = [
    "/osi",
    "/scenarios",
    "/areg",
    "/mass_storage",
    "/sd",
    "/sdcard",
    "/mnt/sd",
    "/mnt/sdcard",
    "/storage/sdcard",
    "/media/sdcard",
    "/mmc",
    "/mmc1",
    "/usb",
]


@dataclass
class DeviceOsiFile:
    """An .osi file discovered on the connected device."""

    name: str
    path: str
    size_bytes: int | None = None
    modified_time: str | None = None


@dataclass
class UploadResult:
    """Result from an OSI file upload operation."""

    ok: bool
    bytes_transferred: int = 0
    remote_path: str | None = None
    error: str | None = None


class DeviceFileService:
    """Queries and manages OSI files on the connected AREG instrument."""

    def __init__(self, scpi_service: ScpiService) -> None:
        self.scpi_service = scpi_service
        self._cached_files: list[DeviceOsiFile] = []

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    async def scan_device_osi_files(
        self,
        directory: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[DeviceOsiFile], str | None]:
        """Query the device file system and return only .osi files.

        Tries the AREG-specific scenario catalog command first, then falls back
        to the generic MMEMory:CATalog? command.

        Returns:
            (list of DeviceOsiFile, error message or None)
        """
        if self._cached_files and not force_refresh:
            return self._cached_files, None

        if not self.scpi_service.transport.connected:
            return [], "Device not connected"

        target_dir = (directory or "").strip() or DEFAULT_SCAN_DIRECTORY

        # 1. Try AREG-specific catalog command
        areg_cmd = f'SOURce1:AREGenerator:SCENario:FILE:CATalog? "{target_dir}"'
        try:
            result = await self.scpi_service.execute_with_classification(areg_cmd)
            if result["ok"] and result.get("response"):
                files = self._parse_catalog_response(str(result["response"]), target_dir)
                if files:
                    self._cached_files = files
                    return files, None
        except Exception:
            pass  # Fall through to generic command

        # 2. Try generic MMEMory:CATalog?
        mmem_cmd = f':MMEMory:CATalog? "{target_dir}"'
        try:
            result = await self.scpi_service.execute_with_classification(mmem_cmd)
            if result["ok"] and result.get("response"):
                files = self._parse_catalog_response(str(result["response"]), target_dir)
                self._cached_files = files
                if not files:
                    return [], None  # Connected, empty directory
                return files, None
            if not result["ok"]:
                error_msg = result.get("error") or "Scan failed"
                return [], str(error_msg)
        except ScpiTransportError as ex:
            return [], f"Transport error during scan: {ex}"
        except Exception as ex:
            return [], f"Scan failed: {ex}"

        return [], None

    def _parse_catalog_response(self, response: str, base_dir: str) -> list[DeviceOsiFile]:
        """Parse SCPI MMEMory:CATalog? or AREG FILE:CATalog? response.

        Supported response formats:
        1. Standard MMEMory: "<free>,<total>","<name>,<type>,<size>","<name>,<type>,<size>"
        2. AREG compact:     "name1.osi,ASC,1234","name2.osi,ASC,5678"
        3. Newline-separated: name1.osi\\nname2.osi
        4. Quoted list:      "name1.osi","name2.osi"

        Only entries whose name ends in .osi are returned.
        """
        files: list[DeviceOsiFile] = []
        if not response or not response.strip():
            return files

        clean = response.strip()

        # Handle simple newline-separated names
        if "\n" in clean and '"' not in clean:
            for line in clean.splitlines():
                name = line.strip()
                if name.lower().endswith(".osi"):
                    files.append(DeviceOsiFile(
                        name=name,
                        path=f"{base_dir.rstrip('/')}/{name}",
                    ))
            return files

        # Split on '","' boundary (quoted CSV entries)
        parts = re.split(r'",\s*"', clean.strip('"'))

        for part in parts:
            if not part:
                continue
            sub = [s.strip().strip('"') for s in part.split(",")]
            if not sub:
                continue
            name = sub[0]
            if not name.lower().endswith(".osi"):
                continue

            size_bytes: int | None = None
            # In MMEMory:CATalog the size is the 3rd field; in AREG it may be 2nd
            for candidate in sub[1:]:
                try:
                    size_bytes = int(candidate.strip())
                    break
                except ValueError:
                    continue

            files.append(DeviceOsiFile(
                name=name,
                path=f"{base_dir.rstrip('/')}/{name}",
                size_bytes=size_bytes,
            ))

        return files

    def get_cached_files(self) -> list[DeviceOsiFile]:
        """Return the last scanned file list without issuing a new query."""
        return list(self._cached_files)

    def clear_cache(self) -> None:
        """Clear the cached file list."""
        self._cached_files = []

    @staticmethod
    def _catalog_parts(response: str) -> list[list[str]]:
        """Split a SCPI catalog response into token lists per entry."""
        if not response or not response.strip():
            return []

        clean = response.strip()
        if "\n" in clean and '"' not in clean:
            return [[line.strip()] for line in clean.splitlines() if line.strip()]

        parts = re.split(r'",\s*"', clean.strip('"'))
        parsed: list[list[str]] = []
        for part in parts:
            if not part:
                continue
            parsed.append([token.strip().strip('"') for token in part.split(",") if token.strip()])
        return parsed

    @staticmethod
    def _normalize_remote_dir(path: str) -> str:
        value = path.strip().replace("\\", "/")
        if not value:
            return "/"
        if value == "/":
            return value
        if re.match(r"^[A-Za-z]:$", value):
            return value
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"

    def _extract_directories_from_catalog_response(self, response: str, base_dir: str = "/") -> list[str]:
        """Extract candidate directory paths from catalog responses."""
        entries = self._catalog_parts(response)
        if not entries:
            return []

        base = self._normalize_remote_dir(base_dir)
        found: list[str] = []

        for tokens in entries:
            if not tokens:
                continue

            name = tokens[0].strip().strip('"')
            name_lower = name.lower()

            # Skip free/total records (e.g. "10000,20000").
            if re.fullmatch(r"\d+", name):
                continue

            token_text = " ".join(tokens).lower()
            is_directory = (
                "/" in name
                or any(tag in token_text for tag in ("dir", "folder"))
                or any(name_lower in p for p in ("sd", "mmc", "mass_storage", "usb", "media", "storage"))
            )

            if not is_directory:
                continue

            if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                full_path = self._normalize_remote_dir(name)
            else:
                parent = "" if base == "/" else base
                full_path = self._normalize_remote_dir(f"{parent}/{name}")

            found.append(full_path)

        return list(dict.fromkeys(found))

    @staticmethod
    def _directory_priority(path: str) -> tuple[int, str]:
        """Sort key: SD-card style paths first, then other directories."""
        lower = path.lower()
        if any(token in lower for token in ("sd", "mmc", "mass_storage")):
            return (0, lower)
        if "usb" in lower:
            return (1, lower)
        if lower == "/":
            return (9, lower)
        return (2, lower)

    async def _is_directory_reachable(self, directory: str) -> bool:
        areg_cmd = f'SOURce1:AREGenerator:SCENario:FILE:CATalog? "{directory}"'
        mmem_cmd = f':MMEMory:CATalog? "{directory}"'

        for cmd in (areg_cmd, mmem_cmd):
            try:
                result = await self.scpi_service.execute_with_classification(cmd)
            except Exception:
                continue
            if bool(result.get("ok")):
                return True
        return False

    async def discover_device_directories(self) -> tuple[list[str], str | None]:
        """Discover reachable scenario directories on the connected device.

        The discovery probes known candidate directories using scenario catalog
        queries. A directory is considered reachable when at least one query
        succeeds, even if the directory currently has zero .osi files.
        """
        if not self.scpi_service.transport.connected:
            return [], "Device not connected"

        root_candidates = ["/", "/mass_storage", "/storage", "/media", "/mnt"]
        discovered_from_catalog: list[str] = []

        # Step 1: pull directory names from reachable root-like catalogs.
        for root in root_candidates:
            areg_cmd = f'SOURce1:AREGenerator:SCENario:FILE:CATalog? "{root}"'
            mmem_cmd = f':MMEMory:CATalog? "{root}"'
            for cmd in (areg_cmd, mmem_cmd):
                try:
                    result = await self.scpi_service.execute_with_classification(cmd)
                except Exception:
                    continue
                if bool(result.get("ok")) and result.get("response"):
                    discovered_from_catalog.extend(
                        self._extract_directories_from_catalog_response(str(result["response"]), base_dir=root)
                    )

        # Step 2: probe extracted directories and common fallback locations.
        probe_candidates = [
            *discovered_from_catalog,
            *FALLBACK_OSI_DIRECTORIES,
        ]
        probe_candidates = [self._normalize_remote_dir(d) for d in probe_candidates]
        probe_candidates = list(dict.fromkeys(probe_candidates))

        reachable: list[str] = []
        for directory in probe_candidates:
            if await self._is_directory_reachable(directory):
                reachable.append(directory)

        if not reachable:
            return [], "No reachable scenario directories discovered"

        unique_dirs = list(dict.fromkeys(reachable))
        unique_dirs.sort(key=self._directory_priority)
        return unique_dirs, None

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_remote_path(remote_path: str) -> str:
        value = (remote_path or "").strip().strip('"')
        value = value.replace("\\", "/")
        value = re.sub(r"/+", "/", value)
        return value

    @staticmethod
    def _build_remote_path_candidates(remote_path: str) -> list[str]:
        """Return likely instrument-compatible path variants for upload.

        Some instruments reject POSIX-like paths such as /usb/foo.osi but accept
        symbolic media roots like USB:/foo.osi or SD:/foo.osi.
        """
        clean = DeviceFileService._sanitize_remote_path(remote_path)
        if not clean:
            return []

        candidates: list[str] = [clean]

        if clean.startswith("/"):
            parts = clean.lstrip("/").split("/", 1)
            root = (parts[0] if parts else "").lower()
            tail = f"/{parts[1]}" if len(parts) > 1 else ""

            aliases: dict[str, list[str]] = {
                "usb": ["USB:", "USB0:", "USB1:"],
                "usb0": ["USB0:", "USB:", "USB1:"],
                "usb1": ["USB1:", "USB:", "USB0:"],
                "sd": ["SD:", "SDCARD:", "MMC:"],
                "sdcard": ["SDCARD:", "SD:", "MMC:"],
                "mmc": ["MMC:", "SD:", "SDCARD:"],
                "mass_storage": ["MMEM:", "MEM:"],
            }

            for alias in aliases.get(root, []):
                candidates.append(f"{alias}{tail}")

        # Preserve order, remove duplicates.
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _is_path_syntax_error(error_text: str | None) -> bool:
        text = (error_text or "").lower()
        return "string data" in text and "not allowed" in text

    @staticmethod
    def _is_media_protected_error(error_text: str | None) -> bool:
        text = (error_text or "").lower()
        return "media protected" in text or "write protect" in text or "read-only" in text

    async def upload_osi_bytes(self, data: bytes, remote_path: str) -> UploadResult:
        """Upload already-loaded .osi bytes to device with path compatibility retries."""
        if not self.scpi_service.transport.connected:
            return UploadResult(ok=False, error="Device is not connected")

        if not data:
            return UploadResult(ok=False, error="File is empty (0 bytes)")

        clean_remote = self._sanitize_remote_path(remote_path)
        if not clean_remote:
            return UploadResult(ok=False, error="Remote destination path is empty")
        if not clean_remote.lower().endswith(".osi"):
            return UploadResult(ok=False, error="Remote path must end with .osi")

        candidates = self._build_remote_path_candidates(clean_remote)
        last_error: str | None = None

        for candidate in candidates:
            result = await self.scpi_service.upload_binary_file(candidate, data)
            if result.get("ok"):
                self.clear_cache()
                return UploadResult(
                    ok=True,
                    bytes_transferred=int(result.get("bytes_transferred", 0)),
                    remote_path=candidate,
                )

            error_text = str(result.get("error") or "Upload failed")
            last_error = error_text

            # Media protection is definitive for that storage; provide explicit guidance.
            if self._is_media_protected_error(error_text):
                return UploadResult(
                    ok=False,
                    remote_path=candidate,
                    error=(
                        "Target media is write-protected on the instrument. "
                        "Use a writable directory (for example internal memory) "
                        "or disable write protection on the removable media. "
                        f"Instrument error: {error_text}"
                    ),
                )

            # If it is a path syntax error, try next candidate variant.
            if self._is_path_syntax_error(error_text):
                continue

        attempted = ", ".join(candidates)
        return UploadResult(
            ok=False,
            error=f"Upload failed. Tried paths: {attempted}. Last error: {last_error or 'unknown error'}",
        )

    async def upload_osi_file(
        self,
        local_path: str,
        remote_path: str,
    ) -> UploadResult:
        """Upload a local .osi file to the device via SCPI :MMEMory:DATA.

        Validates:
        - file extension is .osi
        - file exists locally
        - file is not empty
        - device is connected
        - remote path ends with .osi

        Returns UploadResult with ok=True on success.
        After a successful upload the internal cache is invalidated so the
        next scan call will refresh from the device.
        """
        local = Path(local_path)

        # --- Validate local file ---
        if local.suffix.lower() != ".osi":
            return UploadResult(ok=False, error="File must have a .osi extension")
        if not local.exists():
            return UploadResult(ok=False, error=f"Local file not found: {local_path}")
        if not local.is_file():
            return UploadResult(ok=False, error=f"Path is not a regular file: {local_path}")
        if local.stat().st_size == 0:
            return UploadResult(ok=False, error="File is empty (0 bytes)")

        # --- Validate connection ---
        if not self.scpi_service.transport.connected:
            return UploadResult(ok=False, error="Device is not connected")

        try:
            data = local.read_bytes()
        except OSError as ex:
            return UploadResult(ok=False, error=f"Cannot read local file: {ex}")

        try:
            return await self.upload_osi_bytes(data=data, remote_path=remote_path)
        except Exception as ex:
            return UploadResult(ok=False, error=f"Upload error: {ex}")
