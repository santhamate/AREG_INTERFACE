"""Quick verification script for Scenario Generator deployment."""

import sys
from pathlib import Path

print("=" * 60)
print("SCENARIO GENERATOR - FINAL VERIFICATION")
print("=" * 60)

# Check all files exist
files_to_check = [
    "backend/app/core/osi_utils.py",
    "backend/app/core/scenario_templates.py",
    "backend/app/core/scenario_generator_service.py",
    "backend/tests/test_scenario_generator.py",
    "frontend/src/components/ScenarioGenerator.tsx",
    "frontend/src/components/ScenarioGenerator.css",
    "SCENARIO_GENERATOR_IMPLEMENTATION.md",
    "SCENARIO_GENERATOR_QUICK_START.md",
]

print("\n📁 FILE VERIFICATION:")
all_exist = True
for f in files_to_check:
    path = Path(f)
    if path.exists():
        size = path.stat().st_size
        print(f"  ✓ {f} ({size:,} bytes)")
    else:
        print(f"  ✗ {f} (MISSING)")
        all_exist = False

# Check imports
print("\n🔧 IMPORT VERIFICATION:")
try:
    from backend.app.core.osi_utils import (
        check_osi_availability,
        validate_detection_params,
        add_timestamp_interval,
    )

    print("  ✓ osi_utils imports successful")
except Exception as e:
    print(f"  ✗ osi_utils import failed: {e}")
    all_exist = False

try:
    from backend.app.core.scenario_templates import (
        RangeSweepTemplate,
        ConstantObjectTemplate,
        AzimuthSweepTemplate,
    )

    print("  ✓ scenario_templates imports successful")
except Exception as e:
    print(f"  ✗ scenario_templates import failed: {e}")
    all_exist = False

try:
    from backend.app.core.scenario_generator_service import ScenarioGeneratorService

    print("  ✓ scenario_generator_service imports successful")
except Exception as e:
    print(f"  ✗ scenario_generator_service import failed: {e}")
    all_exist = False

try:
    from backend.app.api.routes import generator_service

    print("  ✓ API routes integration successful")
except Exception as e:
    print(f"  ✗ API routes integration failed: {e}")
    all_exist = False

# Check OSI availability
print("\n🔍 OSI3 STATUS:")
from backend.app.core.osi_utils import check_osi_availability

available, error = check_osi_availability()
if available:
    print("  ✓ OSI3 package installed and ready")
else:
    print("  ⚠ OSI3 not available (graceful degradation active)")

# Check service state
print("\n🎯 SERVICE STATUS:")
from backend.app.core.scenario_generator_service import ScenarioGeneratorService

service = ScenarioGeneratorService()
status = service.get_status()
print("  ✓ Service initialized")
print(f"  ✓ OSI Available: {status.get('osi_available', False)}")

# Summary
print("\n" + "=" * 60)
if all_exist:
    print("✅ ALL SYSTEMS GO - Ready for Testing!")
    print("=" * 60)
    print("\nNEXT STEPS:")
    print("1. Start backend: python -m uvicorn backend.app.main:app --reload")
    print("2. Start frontend: cd frontend && npm run dev")
    print("3. Open http://127.0.0.1:5173")
    print('4. Click "🎬 Scenario Generator" tab')
    print("5. Generate your first scenario!")
    sys.exit(0)
else:
    print("❌ VERIFICATION FAILED - Check errors above")
    sys.exit(1)
