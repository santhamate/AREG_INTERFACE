from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.core.scenario_player import ScenarioPlayerService
from backend.app.core.scpi_service import ScpiService


def make_mock_scpi() -> ScpiService:
    svc = ScpiService.__new__(ScpiService)
    svc.settings = MagicMock()
    svc.settings.command_timeout_ms = 1000
    transport = MagicMock()
    transport.connected = True
    svc.transport = transport
    return svc


@pytest.mark.asyncio
async def test_set_loop_mode_sends_write_without_waiting_for_response() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE LOOP",
        "command_type": "write",
        "response": None,
        "message": "Command sent",
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    ok, _ = await service.set_scenario_replay_mode("LOOP")

    assert ok is True
    scpi.execute_with_classification.assert_called_once_with("SOURce1:AREGenerator:SCENario:REPLay:MODE LOOP")
    last = service.get_command_log()[-1]
    assert last.command_type == "write"
    assert last.waited_for_response is False


@pytest.mark.asyncio
async def test_set_single_mode_sends_write_without_waiting_for_response() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE SINGle",
        "command_type": "write",
        "response": None,
        "message": "Command sent",
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    ok, _ = await service.set_scenario_replay_mode("SINGle")

    assert ok is True
    scpi.execute_with_classification.assert_called_once_with("SOURce1:AREGenerator:SCENario:REPLay:MODE SINGle")
    last = service.get_command_log()[-1]
    assert last.command_type == "write"
    assert last.waited_for_response is False


@pytest.mark.asyncio
async def test_query_replay_mode_sends_query_and_waits_for_response() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE?",
        "command_type": "query",
        "response": "LOOP",
        "message": None,
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    mode = await service.query_scenario_replay_mode()

    assert mode == "LOOP"
    scpi.execute_with_classification.assert_called_once_with("SOURce1:AREGenerator:SCENario:REPLay:MODE?")
    last = service.get_command_log()[-1]
    assert last.command_type == "query"
    assert last.waited_for_response is True


@pytest.mark.asyncio
async def test_query_response_loop_updates_mode() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE?",
        "command_type": "query",
        "response": "LOOP",
        "message": None,
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    mode = await service.query_scenario_replay_mode()

    assert mode == "LOOP"
    assert service.current_replay_mode == "LOOP"


@pytest.mark.asyncio
async def test_query_response_single_updates_mode() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE?",
        "command_type": "query",
        "response": "SINGle",
        "message": None,
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    mode = await service.query_scenario_replay_mode()

    assert mode == "SINGle"
    assert service.current_replay_mode == "SINGle"


@pytest.mark.asyncio
async def test_query_unexpected_response_sets_unknown() -> None:
    scpi = make_mock_scpi()
    scpi.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "SOURce1:AREGenerator:SCENario:REPLay:MODE?",
        "command_type": "query",
        "response": "RANDOM",
        "message": None,
        "error": None,
    })
    service = ScenarioPlayerService(scpi)

    mode = await service.query_scenario_replay_mode()

    assert mode == "UNKNOWN"
    assert service.current_replay_mode == "UNKNOWN"


@pytest.mark.asyncio
async def test_replay_mode_preserved_when_scenario_selection_changes() -> None:
    scpi = make_mock_scpi()
    service = ScenarioPlayerService(scpi)

    service.desired_replay_mode = "LOOP"
    ok_a, _ = await service.select_scenario("/var/user/a.osi")
    ok_b, _ = await service.select_scenario("/var/user/b.osi")

    assert ok_a is True and ok_b is True
    assert service.desired_replay_mode == "LOOP"
