# Scenario Generator - Quick Start Guide

## Installation (5 minutes)

### 1. Install OSI Python Bindings (Optional but Recommended)

The Python import module is `osi3`, but there is no published PyPI package named `osi3`.
Use the official ASAM OSI Python setup instructions:

https://opensimulationinterface.github.io/osi-antora-generator/asamosi/latest/interface/setup/setting_up_osi_python.html

If you skip this, the application will work but show an error in the Scenario Generator with installation instructions.

### 2. No Other Dependencies
All other dependencies are already included in your environment.

## Starting the Application

### Backend
```bash
cd c:\Users\santham\Documents\GitHub\AREG_CONTROL_INTERFACE
python -m uvicorn backend.app.main:app --reload
```
Backend will be available at: `http://127.0.0.1:8000`

### Frontend (New Terminal)
```bash
cd c:\Users\santham\Documents\GitHub\AREG_CONTROL_INTERFACE\frontend
npm run dev
```
Frontend will be available at: `http://127.0.0.1:5173`

## Using Scenario Generator

### Step 1: Open Application
Open your browser to `http://127.0.0.1:5173`

### Step 2: Click "🎬 Scenario Generator" Tab
Located in the top-right corner of the application.

### Step 3: Select a Template

**Range Sweep** - Object moving toward/away from radar
- Example: Target approaching at 10 m/s from 120m to 20m

**Constant Object** - Stationary object
- Example: Target at fixed 100m, no movement

**Multi-Object** - Multiple targets with independent range/velocity/RCS/angle parameters

**Azimuth Sweep** - Object rotating around radar over a configurable angular span

### Step 4: Configure Parameters

For **Range Sweep**:
```
Start Range: 120 m          (initial distance)
Stop Range: 20 m            (final distance)
Velocity: -10 m/s           (negative = toward radar)
RCS: 10 dBsm                (cross section)
Azimuth: 0°                 (straight ahead)
Elevation: 0°               (horizontal)
Update Interval: 0.1 s      (message frequency, min 0.01 s)
```

For **Constant Object**:
```
Range: 100 m                (constant distance)
Duration: 10 s              (how long to maintain)
Velocity: 0 m/s             (0 = stationary)
RCS: 10 dBsm
Azimuth: 0°
Elevation: 0°
Update Interval: 0.1 s
```

### Step 5: Preview (Optional)
Right panel shows estimated:
- Duration and message count
- Range, azimuth, velocity, RCS extremes
- File size estimate
- Any warnings

### Step 6: Generate
Click **"Generate"** button.

You'll see:
- ✅ Success message with file path
- ❌ Error message if issues (with suggestions)

### Step 7: Use in Scenario Player
Generated `.osi` files can now be:
1. Loaded into the Scenario Player
2. Played on the connected AREG800A
3. Monitored and controlled as usual

## Common Scenarios

### Scenario 1: Approaching Target
```
Type: Range Sweep
Start: 300 m, Stop: 50 m
Velocity: -50 m/s (10 km/h approach)
Duration: ~5 seconds
Update: 0.05 s (20 messages/sec)
```

### Scenario 2: Hovering Drone
```
Type: Constant Object
Range: 150 m
Duration: 30 s
Velocity: 0 m/s
Update: 0.1 s (10 messages/sec)
Azimuth: 45° (offset angle)
```

### Scenario 3: Orbiting Target
```
Type: Azimuth Sweep
Range: 200 m
Start Azimuth: -90°
Stop Azimuth: 90°
Duration: 10 s
Update: 0.1 s
```

### Scenario 4: Two Targets
```
Type: Multi-Object
Object 1: Approaching 150→100m, -20 m/s, 0° azimuth
Object 2: Receding 100→200m, +15 m/s, 90° azimuth
Duration: 5 s
Update: 0.05 s
```

## Validation And Transfer APIs

Validate an existing `.osi` file (defaults to last generated if no path is provided):

```bash
curl -X POST http://127.0.0.1:8000/api/generator/validate \
  -H "Content-Type: application/json" \
  -d "{\"file_path\":\"./scenarios/range_sweep.osi\"}"
```

Transfer a generated `.osi` file using local copy adapter:

```bash
curl -X POST http://127.0.0.1:8000/api/generator/transfer \
  -H "Content-Type: application/json" \
  -d "{\"local_path\":\"./scenarios/range_sweep.osi\",\"remote_path\":\"./transfer_out/range_sweep.osi\",\"transfer_method\":\"local_copy\"}"
```

## Parameter Validation

The application checks:

| Check | Min | Max | Error |
|-------|-----|-----|-------|
| Update Interval | 0.01 s | - | "Must be ≥ 0.01 s" |
| Range | 0 m | 10,000 m | "Invalid range" |
| Azimuth | -180° | 360° | "Invalid azimuth" |
| Elevation | -90° | 90° | "Invalid elevation" |
| RCS | -1000 dBsm | 100 dBsm | "Invalid RCS" |
| Velocity | -500 m/s | 500 m/s | "Invalid velocity" |

**Warnings** (non-fatal):
- Velocity/range direction mismatch
- Out-of-field-of-view angles
- Extreme parameter values

## Troubleshooting

### "OSI3 not installed"
Use the official ASAM OSI Python setup instructions (link above), then restart the application.

### "Cannot write to directory"
- Ensure output directory path is valid
- Check write permissions
- Try absolute path instead of relative

### "Update interval too small"
- Minimum is 0.01 s (10 milliseconds)
- AREG cannot process messages faster

### "Invalid range/azimuth/elevation"
- Check parameter values in table above
- Azimuth wraps at ±180°
- Elevation limited to ±90° (hemisphere)

### File not created
- Check application error message for details
- Look at browser console for API errors
- Verify OSI3 bindings are installed: `python -c "import osi3; print('OK')"`

## Advanced Usage

### Via API (Developers)

Generate Range Sweep via curl:
```bash
curl -X POST http://127.0.0.1:8000/api/generator/range-sweep \
  -H "Content-Type: application/json" \
  -d '{
    "output_dir": "./scenarios",
    "output_filename": "test",
    "start_range_m": 120,
    "stop_range_m": 20,
    "radial_velocity_mps": -10,
    "update_interval_s": 0.1
  }'
```

Check generator status:
```bash
curl http://127.0.0.1:8000/api/generator/status
```

View generation logs:
```bash
curl http://127.0.0.1:8000/api/generator/logs?limit=10
```

### OpenAPI Documentation
Full API documentation at: `http://127.0.0.1:8000/docs`

## File Format

Generated `.osi` files are binary protobuf format with IEEE 488.2 structure:
- 4-byte length prefix (little-endian)
- Followed by serialized SensorData message
- Repeats for each timestamp

Not readable as text. Use in Scenario Player to view/play.

## Testing

Run unit tests:
```bash
cd backend
python -m pytest tests/test_scenario_generator.py -v
```

Tests cover:
- Timestamp handling
- Parameter validation  
- File format verification
- Template generation
- Error handling

## API Reference

See full documentation at `SCENARIO_GENERATOR_IMPLEMENTATION.md` or `http://127.0.0.1:8000/docs`

### Endpoints
- `GET /api/generator/status` - Check availability
- `POST /api/generator/range-sweep` - Generate sweep
- `POST /api/generator/constant-object` - Generate constant
- `POST /api/generator/multi-object` - Generate multi-object
- `POST /api/generator/azimuth-sweep` - Generate azimuth
- `GET /api/generator/logs` - View history

## Tips & Tricks

1. **Preview first** - Check right panel before generating
2. **Start simple** - Begin with Constant Object to verify setup
3. **Use standard intervals** - 0.05 s, 0.1 s, 0.2 s are typical
4. **Watch for warnings** - Yellow warnings indicate potential issues
5. **Monitor file size** - Very long durations create large files
6. **Test on AREG** - Verify generated scenarios work with your device

## Next Steps

1. ✅ **Now**: Generate your first scenario
2. ⏳ **Soon**: Multi-Object and Azimuth templates UI
3. ⏳ **Soon**: Direct file transfer to AREG
4. ⏳ **Soon**: Scenario visualization & plotting

## Support

For issues:
1. Check this guide for common problems
2. Review error messages from the application
3. Check `SCENARIO_GENERATOR_IMPLEMENTATION.md` for detailed docs
4. Run unit tests: `pytest tests/test_scenario_generator.py -v`

---

**Ready to generate scenarios? Click "🎬 Scenario Generator" to start!**
