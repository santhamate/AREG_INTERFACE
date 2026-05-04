# Hardcopy / Screenshot Capture Feature

## Overview

The Hardcopy feature allows users to capture the current screen display from the AREG800A instrument and save it as a local image file (PNG, JPG, or BMP).

The feature integrates seamlessly with the existing SCPI command system and maintains the strict query/write separation:
- Configuration commands (`:HCOPY:IMAGE:FORMAT`) are write-only (no response wait)
- Execute command (`:HCOPY:EXECUTE`) is write-only (no response wait)
- Data retrieval command (`:HCOPY:DATA?`) is a query (waits for binary image data)

## User Interface

### Location
- Main app: Click the **📸 Hardcopy** tab in the top-right view selector

### Components
1. **Image Format Selector**
   - Dropdown with supported formats (PNG, JPG, BMP)
   - Fetched from backend based on instrument capabilities

2. **Save Directory**
   - Text input with "Browse" button
   - Default: `./screenshots`
   - Auto-creates directory if it doesn't exist

3. **Filename Prefix**
   - Text input for custom prefix
   - Default: `AREG800A_screenshot`
   - Example: `AREG800A_screenshot_2026-04-27_09-15-30.png`

4. **Auto-Timestamp Checkbox**
   - When enabled (default): Adds date and time to filename
   - Format: `YYYY-MM-DD_HH-MM-SS`
   - When disabled: Uses prefix only + extension

5. **Open After Save Checkbox**
   - When enabled: Opens file explorer showing the saved file
   - Default: Disabled

6. **Filename Preview**
   - Shows exact filename that will be generated
   - Updates in real-time as settings change

7. **Connection Status**
   - Green indicator: Connected
   - Red indicator: Disconnected
   - Capture button disabled when not connected

8. **Capture Button**
   - Large, prominent button
   - Disabled while capturing
   - Shows "🔄 Capturing..." while in progress

9. **Status Messages**
   - Success (green): `Screenshot saved successfully: ... (123456 bytes)`
   - Error (red): Specific error message from backend
   - Ready (gray): Initial state

10. **Last Capture Info**
    - Shows path, size, and timestamp of most recent capture
    - "No screenshots captured yet" when none exist

11. **SCPI Commands Reference**
    - Shows the exact commands used for transparency
    - Educational reference for advanced users

## Backend Architecture

### Core Service: `HardcopyService`

**File:** `backend/app/core/hardcopy_service.py`

#### Key Methods

```python
async def capture_hardcopy(
    save_dir: str | None = None,
    file_format: str = "PNG",
    filename_prefix: str = "AREG800A_screenshot",
    use_timestamp: bool = True,
    timeout_ms: int | None = None,
) -> dict[str, Any]
```

Returns:
```python
{
    "ok": bool,                    # Success status
    "file_path": str | None,       # Path to saved file
    "file_format": str | None,     # Format used
    "bytes_written": int,          # Number of bytes written
    "message": str | None,         # Success message
    "error": str | None,           # Error message if failed
}
```

#### Features

1. **Format Support**
   - PNG (default)
   - JPG/JPEG
   - BMP
   - Extensible design for additional formats

2. **Binary Data Handling**
   - Uses `transport.query_bytes()` for proper binary reception
   - Does NOT decode binary image data as UTF-8 text
   - Handles IEEE 488.2 binary block format if present

3. **Image Validation**
   - Empty payload detection
   - Magic byte validation (PNG: `89 50 4E 47`, JPG: `FF D8`, BMP: `42 4D`)
   - File size verification after write

4. **Error Handling**
   - Connection validation
   - Format validation
   - Directory creation with fallback
   - SCPI command error checking
   - File write validation
   - Comprehensive error messages

5. **Filename Generation**
   - Automatic timestamp with format `YYYY-MM-DD_HH-MM-SS`
   - Customizable prefix
   - Safe filesystem characters only
   - Extension automatic based on format

### API Endpoints

#### 1. Capture Screenshot
```
POST /api/hardcopy/capture

Request:
{
    "save_dir": "./screenshots" | null,
    "file_format": "PNG" | "JPG" | "BMP",
    "filename_prefix": "AREG800A_screenshot",
    "use_timestamp": true,
    "timeout_ms": 5000 | null
}

Response:
{
    "ok": boolean,
    "file_path": string | null,
    "file_format": string | null,
    "bytes_written": number,
    "transport": string,
    "message": string | null,
    "error": string | null
}
```

#### 2. Get Supported Formats
```
GET /api/hardcopy/formats

Response:
{
    "formats": ["PNG", "JPG", "BMP"]
}
```

#### 3. Get Last Capture Info
```
GET /api/hardcopy/last-capture

Response:
{
    "ok": boolean,
    "file_path": string | null,
    "file_size": number,
    "modified_time": number | null
}
```

## SCPI Commands Used

### Command Sequence

1. **Set Image Format** (Write Command)
   ```
   :HCOPY:IMAGE:FORMAT PNG
   ```
   - Sets the output format on the instrument
   - No response expected (write-only)
   - Timeout: 5000ms (or configured)

2. **Execute Hardcopy** (Write Command)
   ```
   :HCOPY:EXECUTE
   ```
   - Triggers the screenshot operation on the instrument
   - Instrument captures current display to memory
   - No response expected (write-only)
   - Timeout: 5000ms (or configured)

3. **Retrieve Image Data** (Query Command)
   ```
   :HCOPY:DATA?
   ```
   - Retrieves the binary image data from the instrument
   - Returns binary block (potentially with IEEE 488.2 header)
   - Waits for response (query)
   - Timeout: 5000ms (or configured)

### Manual SCPI Integration

You can also use these commands through the "Manual SCPI" tab:

```
Manual commands ending with ? use query (wait for response)
Manual commands not ending with ? use write (fire-and-forget)

Examples:
- :HCOPY:IMAGE:FORMAT PNG    (write - no response)
- :HCOPY:EXECUTE             (write - no response)
- :HCOPY:DATA?               (query - binary response, not text)
```

**Note:** `HCOPy:DATA?` returns binary image data. The manual SCPI interface may not display binary data correctly. Use the Hardcopy panel for proper screenshot capture.

## Data Models

### `HardcopyRequest`
```python
class HardcopyRequest(BaseModel):
    save_dir: str | None         # Directory for saving. Defaults to ./screenshots
    file_format: str             # Image format: PNG, JPG, BMP
    filename_prefix: str         # Prefix for generated filename
    use_timestamp: bool          # Add YYYY-MM-DD_HH-MM-SS to filename
    timeout_ms: int | None       # Command timeout
    save_path: str | None        # Legacy: for backward compatibility
```

### `HardcopyResponse`
```python
class HardcopyResponse(BaseModel):
    ok: bool                     # Success status
    file_path: str | None        # Path to saved file
    file_format: str | None      # Format used
    bytes_written: int           # Bytes written to disk
    transport: str | None        # Transport type (HiSLIP, Socket, etc.)
    message: str | None          # Success message
    error: str | None            # Error message
```

## Technical Details

### Binary Data Transfer

The feature handles binary image data correctly:

1. **Query Command:** `HCOPy:DATA?` returns binary image bytes
2. **Transport Layer:** Uses `query_bytes()` which properly receives binary data
3. **IEEE 488.2 Compliance:** Handles block data format if present
4. **No Corruption:** Does NOT attempt UTF-8 decoding on binary image data

### Directory Handling

```python
# If directory doesn't exist, it's created automatically:
Path("./screenshots").mkdir(parents=True, exist_ok=True)

# Supports nested paths:
Path("C:/Users/YourUser/Pictures/AREG_Screenshots").mkdir(parents=True, exist_ok=True)

# Expands ~ to home directory:
Path("~/screenshots").expanduser().mkdir(parents=True, exist_ok=True)
```

### Image Validation

After receiving binary data, the service validates:

1. **Non-Empty:** File must contain data
2. **Magic Bytes:** (Optional, non-blocking)
   - PNG: `89 50 4E 47` (first 4 bytes)
   - JPG: `FF D8 FF` (first 3 bytes)
   - BMP: `42 4D` (first 2 bytes)
3. **File Write:** Bytes actually written to disk
4. **File Exists:** File created successfully

## Configuration

### Default Settings

| Setting | Value |
|---------|-------|
| Save Directory | `./screenshots` |
| Default Format | `PNG` |
| Filename Prefix | `AREG800A_screenshot` |
| Auto-Timestamp | Enabled |
| Open After Save | Disabled |
| Command Timeout | 5000 ms |

### Environment Variables

Currently, all settings are configured through the UI. Future versions may support:

```bash
HARDCOPY_SAVE_DIR=~/Pictures/Screenshots
HARDCOPY_DEFAULT_FORMAT=PNG
HARDCOPY_TIMEOUT_MS=10000
```

## Error Messages

| Error | Cause | Resolution |
|-------|-------|-----------|
| "Instrument not connected" | No active SCPI connection | Connect to the device first |
| "Unsupported format: GIF" | Requested format not supported | Choose PNG, JPG, or BMP |
| "Failed to create save directory" | Permission denied or path invalid | Check directory permissions |
| "Failed to set hardcopy format" | SCPI command error | Check instrument status |
| "Failed to execute hardcopy" | Hardcopy operation failed on device | Check instrument state |
| "Failed to retrieve image data" | Binary data reception failed | Check network/connection |
| "Received empty image data" | Device returned no data | Retry or check instrument |
| "Image file was not written correctly" | Disk I/O error | Check disk space and permissions |

## Testing

### Unit Tests
See `backend/tests/test_hardcopy.py`

Run tests:
```bash
cd backend
python -m pytest tests/test_hardcopy.py -v
```

### Manual Testing Checklist

1. **Basic Capture**
   - [ ] Connect to instrument
   - [ ] Click "Capture Screenshot"
   - [ ] File appears in default ./screenshots directory
   - [ ] File is valid PNG (can open in image viewer)

2. **Format Selection**
   - [ ] Change format to JPG, capture
   - [ ] File is .jpg and opens correctly
   - [ ] Change format to BMP, capture
   - [ ] File is .bmp and opens correctly

3. **Custom Directory**
   - [ ] Click Browse, select custom directory
   - [ ] Capture
   - [ ] File appears in selected directory

4. **Filename Customization**
   - [ ] Change prefix to "MyScreenshot"
   - [ ] Disable timestamp
   - [ ] Capture
   - [ ] Filename is exactly "MyScreenshot.png"
   - [ ] Enable timestamp
   - [ ] Capture
   - [ ] Filename contains date/time

5. **Error Handling**
   - [ ] Disconnect from instrument
   - [ ] Try to capture
   - [ ] Error: "Instrument not connected"
   - [ ] Reconnect
   - [ ] Capture succeeds

6. **Last Capture Info**
   - [ ] Capture a screenshot
   - [ ] "Last Capture" section shows file path, size, time

7. **Edge Cases**
   - [ ] Create read-only directory, try to capture → Error
   - [ ] Fill disk space, try to capture → Error
   - [ ] Very long filename prefix → File created successfully

## Troubleshooting

### Issue: "Capture Screenshot" button is grayed out

**Cause:** Instrument is not connected

**Solution:**
1. Go to "Manual SCPI" tab
2. Enter connection settings (Host, Port)
3. Click "Connect"
4. Return to "Hardcopy" tab

### Issue: File is saved but appears corrupted

**Cause:** Binary data was incorrectly transferred or decoded

**Solution:**
1. Verify instrument is functioning (use Manual SCPI to query `*IDN?`)
2. Try a different format (PNG → JPG)
3. Check available disk space
4. Restart the application and try again

### Issue: Screenshot is blank or shows wrong content

**Cause:** Instrument had no display or was in wrong mode when capturing

**Solution:**
1. Verify the instrument screen shows content
2. Check that you're capturing the right display area
3. Use the instrument's native screenshot button if available
4. Try capturing again immediately

### Issue: File permissions error

**Cause:** No write permission to save directory

**Solution:**
1. Use Browse button to select a writable directory
2. Check folder permissions on disk
3. Try saving to Documents or Downloads
4. Run application with appropriate permissions

## Advanced Usage

### Using Hardcopy in Scripts

```python
from backend.app.core.hardcopy_service import HardcopyService
from backend.app.core.scpi_service import ScpiService

# Create service
scpi = ScpiService()
hardcopy = HardcopyService(scpi)

# Capture with custom settings
result = await hardcopy.capture_hardcopy(
    save_dir="/path/to/screenshots",
    file_format="PNG",
    filename_prefix="TEST_CAP",
    use_timestamp=True,
    timeout_ms=10000,
)

if result["ok"]:
    print(f"Saved: {result['file_path']} ({result['bytes_written']} bytes)")
else:
    print(f"Error: {result['error']}")
```

### Batch Capture

```python
# Capture multiple screenshots in sequence
for i in range(5):
    result = await hardcopy.capture_hardcopy(
        filename_prefix=f"batch_{i:02d}_screenshot"
    )
    print(f"Capture {i}: {result['ok']}")
    await asyncio.sleep(1)  # Wait between captures
```

### Custom Filename Pattern

Currently supported pattern:
```
<prefix>_YYYY-MM-DD_HH-MM-SS.<ext>
```

Future enhancement: Support for custom patterns like:
```
<prefix>_<timestamp>_<counter>.<ext>
```

## Performance Notes

- Capture time depends on image format and instrument:
  - PNG (lossless): ~500-1000 ms
  - JPG (compressed): ~300-700 ms
  - BMP (uncompressed): ~200-500 ms
- Network latency affects transfer time
- File size typically:
  - PNG: 100-500 KB
  - JPG: 30-150 KB
  - BMP: 500 KB - 2 MB

## Future Enhancements

- [ ] Image thumbnail preview
- [ ] Gallery view of captured screenshots
- [ ] Automatic screenshot scheduling
- [ ] Annotate screenshots (arrows, text, highlighting)
- [ ] Integrate with cloud storage (OneDrive, Google Drive)
- [ ] Watermarking with timestamp/device ID
- [ ] OCR to extract text from screenshots
- [ ] Batch processing / multiple captures
- [ ] Resolution/quality adjustment
- [ ] Rotate/flip options

## Related Features

- **Scenario Player:** For automating test scenarios
- **Manual SCPI:** For low-level command testing
- **Command Reference:** For SCPI documentation

## Contact & Support

For issues or feature requests related to the Hardcopy feature, refer to the main project documentation.
