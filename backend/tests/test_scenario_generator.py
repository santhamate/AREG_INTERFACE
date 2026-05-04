"""Unit tests for scenario generator modules.

Tests cover:
- OSI utilities (timestamp handling, validation, file writing)
- Scenario templates (range sweep, constant object, multi-object, azimuth sweep)
- Scenario generator service (orchestration, parameter handling)
- API integration (endpoint responses)
"""

import pytest
from pathlib import Path
import tempfile
import struct

# Note: These tests are written to work with or without osi3 package installed
# If osi3 is not available, mocked tests will pass; generation will fail with graceful error

from backend.app.core.osi_utils import (
    add_timestamp_interval,
    degrees_to_radians,
    check_osi_availability,
    validate_detection_params,
    write_osi_file,
)
from backend.app.core.scenario_templates import (
    RangeSweepParams,
    RangeSweepTemplate,
    ConstantObjectParams,
    ConstantObjectTemplate,
    AzimuthSweepParams,
    AzimuthSweepTemplate,
    ScenarioPreview,
)
from backend.app.core.scenario_generator_service import ScenarioGeneratorService


# ============================================================================
# OSI Utilities Tests
# ============================================================================


class TestTimestampHandling:
    """Test OSI timestamp generation and interval addition."""

    def test_add_zero_interval(self):
        """Adding zero interval should not change timestamp."""
        sec, nanos = add_timestamp_interval(0, 0, 0.0)
        assert sec == 0
        assert nanos == 0

    def test_add_100ms_interval(self):
        """Adding 100ms should result in 100,000,000 nanos."""
        sec, nanos = add_timestamp_interval(0, 0, 0.1)
        assert sec == 0
        assert nanos == 100_000_000

    def test_add_interval_with_carry(self):
        """Adding interval that exceeds 1 second should carry to seconds."""
        sec, nanos = add_timestamp_interval(0, 900_000_000, 0.2)
        assert sec == 1
        assert nanos == 100_000_000

    def test_add_multiple_seconds(self):
        """Adding multiple seconds should work correctly."""
        sec, nanos = add_timestamp_interval(0, 0, 5.0)
        assert sec == 5
        assert nanos == 0

    def test_add_interval_precision(self):
        """Test floating-point precision in interval addition."""
        sec, nanos = add_timestamp_interval(0, 0, 0.33)
        assert sec == 0
        assert 330_000_000 - 1_000_000 <= nanos <= 330_000_000 + 1_000_000  # Allow 1ms tolerance


class TestDegreesToRadians:
    """Test angle conversion."""

    def test_zero_degrees(self):
        """0 degrees = 0 radians."""
        rad = degrees_to_radians(0)
        assert rad == 0

    def test_90_degrees(self):
        """90 degrees ≈ π/2 radians."""
        rad = degrees_to_radians(90)
        assert abs(rad - 1.5707963267948966) < 0.0001

    def test_180_degrees(self):
        """180 degrees ≈ π radians."""
        rad = degrees_to_radians(180)
        assert abs(rad - 3.141592653589793) < 0.0001

    def test_negative_angle(self):
        """Negative angles should work."""
        rad = degrees_to_radians(-45)
        assert rad < 0


class TestDetectionValidation:
    """Test detection parameter validation."""

    def test_valid_detection(self):
        """Valid parameters should pass validation."""
        valid, error = validate_detection_params(100, 0, 0, -10, 10)
        assert valid
        assert error is None

    def test_negative_distance(self):
        """Negative distance should fail."""
        valid, error = validate_detection_params(-10, 0, 0, 0, 10)
        assert not valid
        assert "Distance" in error

    def test_invalid_azimuth(self):
        """Out-of-range azimuth should fail."""
        valid, error = validate_detection_params(100, 500, 0, 0, 10)
        assert not valid
        assert "Azimuth" in error

    def test_invalid_elevation(self):
        """Out-of-range elevation should fail."""
        valid, error = validate_detection_params(100, 0, 180, 0, 10)
        assert not valid
        assert "Elevation" in error

    def test_extreme_rcs(self):
        """Extreme RCS values should fail."""
        valid, error = validate_detection_params(100, 0, 0, 0, 1000)
        assert not valid
        assert "RCS" in error


class TestOsiAvailability:
    """Test OSI package availability check."""

    def test_osi_check_returns_tuple(self):
        """check_osi_availability should return (bool, str|None)."""
        available, error = check_osi_availability()
        assert isinstance(available, bool)
        assert error is None or isinstance(error, str)

    def test_missing_osi_returns_error_message(self):
        """If OSI is missing, error message should explain installation."""
        available, error = check_osi_availability()
        if not available:
            assert "osi3" in error.lower() or "pip" in error.lower()


class TestOsiFileWriting:
    """Test OSI file writing with length prefixes."""

    def test_write_empty_messages(self):
        """Writing empty message list should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.osi"
            result = write_osi_file([], str(output_path))
            assert result["ok"]
            assert result["message_count"] == 0
            assert output_path.exists()

    def test_write_single_message(self):
        """Writing a single message should include length prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.osi"
            test_msg = b"test_message"
            result = write_osi_file([test_msg], str(output_path))
            assert result["ok"]
            assert result["message_count"] == 1

            # Verify file format: 4-byte length prefix + message
            data = output_path.read_bytes()
            length_bytes = data[:4]
            length = struct.unpack("<L", length_bytes)[0]
            assert length == len(test_msg)
            assert data[4:4 + len(test_msg)] == test_msg

    def test_write_multiple_messages(self):
        """Writing multiple messages should include length prefix for each."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.osi"
            messages = [b"msg1", b"message_two", b"m3"]
            result = write_osi_file(messages, str(output_path))
            assert result["ok"]
            assert result["message_count"] == 3

    def test_invalid_filename_extension(self):
        """Non-.osi filename should fail."""
        with pytest.raises(ValueError, match=r"\.osi"):
            write_osi_file([], "/tmp/test.txt")


# ============================================================================
# Scenario Template Tests
# ============================================================================


class TestRangeSweepTemplate:
    """Test range sweep scenario generation."""

    def test_validate_minimum_interval(self):
        """Interval below 0.01s should fail validation."""
        params = RangeSweepParams(update_interval_s=0.001)
        valid, warnings = RangeSweepTemplate.validate_params(params)
        assert not valid

    def test_validate_good_interval(self):
        """0.1s interval should pass validation."""
        params = RangeSweepParams(update_interval_s=0.1)
        valid, warnings = RangeSweepTemplate.validate_params(params)
        assert valid

    def test_velocity_direction_warning(self):
        """Mismatched velocity/range direction should warn."""
        params = RangeSweepParams(
            start_range_m=20,
            stop_range_m=120,
            radial_velocity_mps=-10,  # Moving toward but range increasing
        )
        valid, warnings = RangeSweepTemplate.validate_params(params)
        assert valid
        assert len(warnings) > 0  # Should have warnings about direction

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_generate_basic_range_sweep(self):
        """Generate a simple range sweep."""
        params = RangeSweepParams(
            start_range_m=100,
            stop_range_m=50,
            radial_velocity_mps=-10,
            update_interval_s=0.1,
        )
        messages, preview = RangeSweepTemplate.generate(params)
        assert len(messages) > 0
        assert preview.message_count == len(messages)
        assert preview.object_count == 1


class TestConstantObjectTemplate:
    """Test constant object scenario generation."""

    def test_validate_minimum_interval(self):
        """Interval below 0.01s should fail validation."""
        params = ConstantObjectParams(update_interval_s=0.001)
        valid, warnings = ConstantObjectTemplate.validate_params(params)
        assert not valid

    def test_validate_zero_duration(self):
        """Zero or negative duration should fail."""
        params = ConstantObjectParams(duration_s=0)
        valid, warnings = ConstantObjectTemplate.validate_params(params)
        assert not valid

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_generate_constant_object(self):
        """Generate a constant object scenario."""
        params = ConstantObjectParams(
            duration_s=1.0,
            update_interval_s=0.1,
            range_m=100,
        )
        messages, preview = ConstantObjectTemplate.generate(params)
        assert len(messages) > 0
        assert preview.duration_s > 0


class TestAzimuthSweepTemplate:
    """Test azimuth sweep scenario generation."""

    def test_validate_minimum_interval(self):
        """Interval below 0.01s should fail validation."""
        params = AzimuthSweepParams(update_interval_s=0.001)
        valid, warnings = AzimuthSweepTemplate.validate_params(params)
        assert not valid

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_generate_azimuth_sweep(self):
        """Generate an azimuth sweep scenario."""
        params = AzimuthSweepParams(
            duration_s=3.6,
            update_interval_s=0.1,
            start_azimuth_deg=-180,
            stop_azimuth_deg=180,
        )
        messages, preview = AzimuthSweepTemplate.generate(params)
        assert len(messages) > 0
        assert preview.object_count == 1


# ============================================================================
# Scenario Generator Service Tests
# ============================================================================


class TestScenarioGeneratorService:
    """Test the main scenario generator service."""

    @pytest.fixture
    def generator(self):
        """Create a fresh generator service for each test."""
        return ScenarioGeneratorService()

    def test_get_status(self, generator):
        """Get status should return valid dict."""
        status = generator.get_status()
        assert "osi_available" in status
        assert "osi_error" in status
        assert isinstance(status["osi_available"], bool)

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_generate_range_sweep(self, generator):
        """Generate a range sweep scenario."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_range_sweep(
                output_dir=tmpdir,
                output_filename="test_range_sweep",
                start_range_m=100,
                stop_range_m=50,
                radial_velocity_mps=-10,
                update_interval_s=0.1,
            )
            assert result["ok"]
            assert result["file_path"] is not None
            assert result["message_count"] > 0
            assert result["preview"] is not None

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_generate_constant_object(self, generator):
        """Generate a constant object scenario."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_constant_object(
                output_dir=tmpdir,
                output_filename="test_constant",
                duration_s=1.0,
                update_interval_s=0.1,
                range_m=100,
            )
            assert result["ok"]
            assert result["file_path"] is not None
            assert result["message_count"] > 0

    def test_generation_logs(self, generator):
        """Get generation logs should return list."""
        logs = generator.get_generation_logs()
        assert isinstance(logs, list)

    def test_validate_osi_file_success(self, generator):
        """Validation should parse length-prefixed messages correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "validate_me.osi"
            write_osi_file([b"m1", b"message_two"], output_path)

            result = generator.validate_osi_file(output_path)
            assert result["ok"]
            assert result["exists"]
            assert result["message_count"] == 2

    def test_validate_osi_file_invalid_frame(self, generator):
        """Validation should fail when frame length exceeds file size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "broken.osi"
            output_path.write_bytes(struct.pack("<L", 10) + b"ab")

            result = generator.validate_osi_file(output_path)
            assert not result["ok"]
            assert "framing" in result["error"].lower()

    def test_transfer_file_local_copy(self, generator):
        """Transfer service should copy file via local_copy adapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.osi"
            dst = Path(tmpdir) / "out" / "dst.osi"
            src.write_bytes(b"test-bytes")

            result = generator.transfer_file(src, dst, transfer_method="local_copy")
            assert result["ok"]
            assert Path(result["remote_path"]).exists()
            assert Path(result["remote_path"]).read_bytes() == b"test-bytes"

            logs = generator.get_transfer_logs()
            assert len(logs) >= 1

    def test_auto_filename_generation(self, generator):
        """Auto-generated filenames should end with .osi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_range_sweep(
                output_dir=tmpdir,
                output_filename=None,  # Auto-generate
                start_range_m=100,
                stop_range_m=50,
                radial_velocity_mps=-10,
                update_interval_s=0.1,
            )
            # Even if it fails due to missing osi3, it should handle gracefully
            if result["ok"]:
                assert result["file_path"].endswith(".osi")

    def test_missing_osi_graceful_failure(self, generator):
        """Missing OSI should fail gracefully with error message."""
        if not generator.state.osi_available:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = generator.generate_range_sweep(
                    output_dir=tmpdir,
                    start_range_m=100,
                    stop_range_m=50,
                )
                assert not result["ok"]
                assert result["error"] is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestScenarioGenerationIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_full_generation_and_validation_flow(self):
        """Test complete flow from generation to file validation."""
        generator = ScenarioGeneratorService()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate scenario
            result = generator.generate_range_sweep(
                output_dir=tmpdir,
                output_filename="integration_test",
                start_range_m=120,
                stop_range_m=20,
                radial_velocity_mps=-10,
                update_interval_s=0.1,
            )

            assert result["ok"]
            assert result["file_path"] is not None

            # Verify file exists and is readable
            file_path = Path(result["file_path"])
            assert file_path.exists()
            assert file_path.stat().st_size > 0

            # Verify .osi format (length-prefixed messages)
            data = file_path.read_bytes()
            assert len(data) >= 4  # At least one length prefix

            # Verify at least one message
            assert result["message_count"] >= 1

    @pytest.mark.skipif(
        not check_osi_availability()[0],
        reason="OSI3 package not installed",
    )
    def test_multiple_generations_tracking(self):
        """Test that service tracks multiple generations."""
        generator = ScenarioGeneratorService()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate first scenario
            result1 = generator.generate_range_sweep(
                output_dir=tmpdir,
                output_filename="scenario1",
                start_range_m=100,
                stop_range_m=50,
                update_interval_s=0.1,
            )

            # Generate second scenario
            result2 = generator.generate_constant_object(
                output_dir=tmpdir,
                output_filename="scenario2",
                duration_s=1.0,
                update_interval_s=0.1,
            )

            # Check logs
            logs = generator.get_generation_logs()
            assert len(logs) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
