#!/usr/bin/env python3
"""Test command classification logic (query vs write)."""

def classify_command(command: str) -> str:
    """Classify a command as query or write based on ? character."""
    cleaned = command.strip()
    if not cleaned:
        return "empty"
    return "query" if cleaned.endswith("?") else "write"


def main() -> int:
    """Run standalone command classification checks."""
    test_cases = [
        # Queries
        ("*IDN?", "query"),
        ("SOURce1:AREGenerator:HIL:RATE?", "query"),
        ("SOURce1:AREGenerator:HIL:RECeived?", "query"),
        ("SOURce1:AREGenerator:SCENario:STATe?", "query"),
        ("SYSTem:ERRor?", "query"),
        ("SYSTem:ERRor:ALL?", "query"),

        # Writes
        ("SOURce1:AREGenerator:SCENario:PAUSe", "write"),
        ("SOURce1:AREGenerator:SCENario:PLAY", "write"),
        ("SOURce1:AREGenerator:SCENario:STOP", "write"),
        ("SOURce1:AREGenerator:OSETup:MODE DYNamic", "write"),
        ("SOURce1:AREGenerator:SCENario:LOAD \"example\"", "write"),
        ("SOURce1:AREGenerator:SCENario:SELect \"scenario_name\"", "write"),
        ("*CLS", "write"),
        ("*RST", "write"),

        # Edge cases
        ("", "empty"),
        ("   ", "empty"),
        ("*OPC?", "query"),
    ]

    print("Testing command classification...\n")
    passed = 0
    failed = 0

    for command, expected in test_cases:
        result = classify_command(command)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status}: '{command}' -> {result} (expected {expected})")

    print(f"\n{passed} passed, {failed} failed out of {len(test_cases)} tests")
    if failed == 0:
        print("All tests passed!")
        return 0

    print("Some tests failed!")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
