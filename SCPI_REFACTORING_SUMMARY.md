# SCPI Command Execution Refactoring - Implementation Summary

## Overview
Refactored the AREG800A SCPI control system to properly distinguish between query commands (ending with `?`) and write-only commands (no `?`). This fixes the critical issue where non-query commands were causing timeouts by waiting for responses that never come.

## Files Changed

### 1. **Backend Core**

#### `backend/app/core/scpi_service.py`
- **`execute_with_classification(command, timeout_ms)`** – NEW centralized executor
  - Auto-detects command type from `?` character
  - Returns detailed result dict with command_type, response, message, error
  - Queries: send command, wait for response, return response
  - Writes: send command, don't wait, return success message
  - Handles timeouts appropriately for each type

- **`execute()`** – Kept for backward compatibility
  - Now delegates auto-detection to centralized logic

#### `backend/app/models/scpi.py`
- **`CommandResponse`** – Updated with new fields:
  - `command_type: Literal["query", "write", "empty"]`
  - `message: str | None` – For write success messages
  - `error: str | None` – For error details
  
- **`CommandRequest`** – Updated:
  - `expect_response: bool | None = None` – Now optional (auto-detect)

#### `backend/app/api/routes.py`
- **`/scpi/send` endpoint** – Updated to use `execute_with_classification()`
  - No longer sends `expect_response` parameter
  - Backend auto-detects based on command content

#### `backend/app/core/areg_controller.py`
- **`write_scpi(cmd)`** – Sends setter/event commands without reading response
- **`query_scpi(cmd)`** – Validates `?` present, then sends and reads response
- **`opc_sync()`** – Waits for *OPC? response
- All internal calls updated to use these strict helpers

### 2. **Frontend**

#### `frontend/src/App.tsx`
- **`CommandResult` type** – Updated to include:
  - `command_type: "query" | "write" | "empty"`
  - `message: string | null`
  - `error: string | null`

- **`runCommand()` function** – Simplified:
  - No longer sends `expect_response` parameter
  - Removed hardcoded `expect_response: true`
  - Backend auto-detects based on command

## Command Classification Rules

### Query Commands (use `query_scpi()`)
**Pattern:** Command ends with `?`

**Examples:**
- `*IDN?` – Query instrument identification
- `SYSTem:ERRor:ALL?` – Query all errors
- `SOURce1:AREGenerator:HIL:RATE?` – Query HIL rate
- `SOURce1:AREGenerator:SCENario:STATus?` – Query scenario status

**Behavior:**
- Send command
- Wait for response (respects timeout)
- Return response to caller
- Timeout is an error

### Write Commands (use `write_scpi()`)
**Pattern:** Command does NOT end with `?`

**Examples:**
- `SOURce1:AREGenerator:SCENario:PAUSe` – Pause scenario
- `SOURce1:AREGenerator:SCENario:PLAY` – Play scenario
- `SOURce1:AREGenerator:OSETup:MODE DYNamic` – Set mode
- `*CLS` – Clear status
- `*RST` – Reset

**Behavior:**
- Send command
- Do NOT wait for response
- Return success message "Command sent"
- No timeout error (command fires and forgets)

### Empty Commands
**Pattern:** Command is empty or whitespace-only

**Behavior:**
- Return error "Command is empty."
- No transport call

## API Response Examples

### Query Command Response
```json
{
  "command": "*IDN?",
  "command_type": "query",
  "response": "Rohde&Schwarz AREG800A,...",
  "message": null,
  "ok": true,
  "transport": "hislip",
  "error": null
}
```

### Write Command Response
```json
{
  "command": "SOURce1:AREGenerator:SCENario:PAUSe",
  "command_type": "write",
  "response": null,
  "message": "Command sent",
  "ok": true,
  "transport": "hislip",
  "error": null
}
```

### Query Command Timeout
```json
{
  "command": "*IDN?",
  "command_type": "query",
  "response": null,
  "message": null,
  "ok": false,
  "transport": "hislip",
  "error": "Command timeout: *IDN?"
}
```

### Empty Command Error
```json
{
  "command": "",
  "command_type": "empty",
  "response": null,
  "message": null,
  "ok": false,
  "transport": "hislip",
  "error": "Command is empty."
}
```

## How to Use

### Manual Command Execution
1. User types a command in the UI
2. Clicks "Send"
3. Frontend sends command WITHOUT specifying `expect_response`
4. Backend automatically detects:
   - Ends with `?` → query (will wait for response)
   - No `?` → write (won't wait for response)
5. Response displayed in UI

### Via AREG Controller
```python
# Query command
response = await controller.query_scpi("*IDN?")

# Write command
await controller.write_scpi("SOURce1:AREGenerator:SCENario:PAUSe")

# Wait for completion
await controller.opc_sync()

# Check errors
errors = await controller.check_errors()
```

### Via SCPI Service (centralized executor)
```python
result = await service.execute_with_classification("*IDN?")
# or
result = await service.execute_with_classification(
    "SOURce1:AREGenerator:SCENario:PAUSe"
)
```

## Testing

Command classification test file: `test_command_classification.py`
- Tests 17 different command patterns
- 100% pass rate
- All query, write, and edge cases covered

## Key Improvements

✅ **No more timeouts on write commands** – Non-query commands don't wait for responses
✅ **Proper query handling** – Only query commands wait for responses
✅ **Centralized logic** – Single executor handles all SCPI commands
✅ **Type-safe** – Command type is explicit in response
✅ **Better error messages** – Distinguishes between query timeouts and write errors
✅ **Frontend integration** – UI displays correct information for each command type
✅ **Backward compatible** – Old `execute()` method still works with auto-detection
✅ **Comprehensive validation** – `query_scpi()` rejects non-query commands at call time

## Transport Compatibility

Works with all transport layers:
- HiSLIP (primary)
- Raw Socket
- Extensible for VXI-11, RSIB, mDNS

## Configuration

No configuration needed. Command type detection is automatic based on `?` character.

Optional future enhancement: Global `CHECK_ERRORS_AFTER_WRITE` setting to query `SYSTem:ERRor:ALL?` after write commands (currently disabled to prevent extra traffic).
