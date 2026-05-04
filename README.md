# AREG Control Interface

AREG800A control platform with YAML-backed command execution and hardware-safe SCPI helpers:

1. Standalone raw-socket SCPI execution layer
2. YAML command-source controller for AREG800A setup sequences
3. Automated SCPI catalog ingestion from manuals

## What Is Implemented Now

- FastAPI backend for standalone SCPI command execution
- Raw socket SCPI transport on port 5025
- Real HiSLIP framed transport with sync/async channel setup
- Command catalog loader/validator and ingestion endpoint
- YAML-backed AREG controller for static-object setup with limit probing and error checks
- Scenario graph compiler endpoint
- React frontend shell with:
	- SCPI command send panel
	- Manual ingestion trigger
	- Command reference table

## Project Structure

```
backend/
	app/
		api/routes.py
		core/
			areg_controller.py
			catalog.py
			catalog_ingest.py
			config.py
			hislip.py
			scenario_compiler.py
			scpi_service.py
		models/scpi.py
		models/areg.py
		models/scenario.py
		main.py
	tools/ingest_catalog.py
	catalogs/areg_commands.json
	catalogs/workflow/verification_queue.csv
	requirements.txt
frontend/
	src/
		components/ScenarioCanvas.tsx
		App.tsx
		main.tsx
		styles.css
	package.json
main.py
```

## Run Backend

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Start API:

```bash
python main.py
```

API base: `http://127.0.0.1:8000/api`

4. Connect session to hardware:

```bash
curl -X POST http://127.0.0.1:8000/api/session/connect -H "Content-Type: application/json" -d "{\"host\":\"<AREG_IP>\",\"port\":4880}"
```

5. Send a smoke command:

```bash
curl -X POST http://127.0.0.1:8000/api/scpi/send -H "Content-Type: application/json" -d "{\"command\":\"*IDN?\",\"expect_response\":true}"
```

6. Run the YAML-backed static-object helper over raw socket 5025:

```bash
curl -X POST http://127.0.0.1:8000/api/areg/static-object/setup -H "Content-Type: application/json" -d "{\"host\":\"<AREG_IP>\",\"port\":5025,\"source_hw\":1,\"object_index\":1,\"range_value\":20,\"attenuation\":50,\"doppler_speed\":0,\"angle_horizontal\":0}"
```

## Run Frontend

1. Install Node dependencies:

```bash
cd frontend
npm install
```

2. Start UI:

```bash
npm run dev
```

UI base: `http://127.0.0.1:5173`

Use the UI flow:
1. Click `Ingest Manuals` once to auto-populate catalog and verification queue.
2. Connect backend session to AREG hardware.
3. Use `Standalone SCPI Runner` for ad-hoc commands.
4. Review the command reference table for the YAML command inventory.

## API Endpoints

- `GET /api/health`
- `GET /api/catalog/summary`
- `POST /api/catalog/ingest`
- `GET /api/session`
- `POST /api/session/connect`
- `POST /api/session/disconnect`
- `POST /api/scpi/send`
- `POST /api/areg/static-object/setup`
- `POST /api/scenarios/compile`
- `GET /api/generator/status`
- `POST /api/generator/range-sweep`
- `POST /api/generator/constant-object`
- `POST /api/generator/multi-object`
- `POST /api/generator/azimuth-sweep`
- `POST /api/generator/validate`
- `POST /api/generator/transfer`
- `GET /api/generator/logs`
- `GET /api/generator/transfer-logs`

## Environment Variables

- `AREG_HISLIP_HOST=...` default `127.0.0.1`
- `AREG_HISLIP_PORT=...` default `4880`
- `AREG_SOCKET_HOST=...` default `127.0.0.1`
- `AREG_SOCKET_PORT=...` default `5025`
- `AREG_COMMAND_TIMEOUT_MS=...` default `3000`
- `AREG_COMMAND_SOURCE_PATH=...` default `.venv/commands.yaml`

## Notes

- HiSLIP transport now uses framed messages and dual-channel setup.
- Raw socket controller writes newline-terminated SCPI commands and checks `SYST:ERR?` after each configuration block.
- OCR is not mandatory in the first pass: parser uses PDF text extraction and writes unverified commands to workflow queue.
- Verification queue is generated in `backend/catalogs/workflow/verification_queue.csv`.

