from unittest.mock import Mock

import pytest

from pymitsubishi import DriveMode, MitsubishiController, RemoteLock, SetRemoteTemperature, WindSpeed
from tests.test_fixtures import REAL_DEVICE_XML_RESPONSE


def test_set_power_on():
    """Test a complete cycle of status fetch and device control."""
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    controller.set_power(True)

    mock_api.send_hex_command.assert_called_once_with("fc410130100101020100090000000000000000ac4183")


def test_changeset_does_not_mutate_controller_state_before_apply():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE

    original = controller.fetch_status().general.temperature
    changeset = controller.changeset()
    changeset.set_temperature(21.0)

    assert controller.state.general.temperature == original


def test_command_preserves_desired_state_when_response_is_stale():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    state = controller.set_temperature(21.0)

    assert state.general.temperature == 21.0
    assert controller.state.general.temperature == 21.0


def test_applied_changeset_does_not_alias_controller_state():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    changeset = controller.changeset()
    changeset.set_temperature(21.0)
    controller.apply_changeset(changeset)
    changeset.set_temperature(22.0)

    assert controller.state.general.temperature == 21.0


def test_applied_extend08_changeset_does_not_alias_controller_state():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    changeset = controller.changeset()
    changeset.set_power_saving(True)
    controller.apply_changeset(changeset)
    changeset.set_power_saving(False)

    assert controller.state.general.is_power_saving is True


def test_followup_command_uses_optimistic_state_after_stale_response():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    controller.set_temperature(21.0)
    controller.set_fan_speed(WindSpeed.S3)

    assert controller.state.general.temperature == 21.0
    assert controller.state.general.wind_speed == WindSpeed.S3


def test_auto_mode_command_keeps_enum_state():
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    state = controller.set_mode(DriveMode.AUTO)

    mock_api.send_hex_command.assert_called_once_with("fc410130100102020008090000000000000000ac417b")
    assert state.general.drive_mode == DriveMode.AUTO
    assert controller.state.general.drive_mode == DriveMode.AUTO


@pytest.mark.parametrize(
    "mode, hex_cmd",
    [
        (DriveMode.AUTO, "fc410130100102020008090000000000000000ac417b"),
        (DriveMode.FAN, "fc410130100102020007090000000000000000ac417c"),
        (DriveMode.COOLER, "fc410130100102020003090000000000000000ac4180"),
        (DriveMode.HEATER, "fc410130100102020001090000000000000000ac4182"),
    ],
)
def test_set_auto(mode, hex_cmd):
    """Test a complete cycle of status fetch and device control."""
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    controller.set_mode(mode)

    mock_api.send_hex_command.assert_called_once_with(hex_cmd)


@pytest.mark.parametrize(
    "lock, hex_cmd",
    [
        (RemoteLock.PowerLocked, "fc410130100140020000090000000000010000ac4144"),
    ],
)
def test_set_remote_lock(lock, hex_cmd):
    """Test a complete cycle of status fetch and device control."""
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    controller.set_remote_lock(lock)

    mock_api.send_hex_command.assert_called_once_with(hex_cmd)


def test_set_remote_lock_preserves_cached_general_fields():
    """Test remote lock changes do not drop cached general state fields."""
    mock_api = Mock()
    controller = MitsubishiController(mock_api)
    mock_api.send_status_request.return_value = REAL_DEVICE_XML_RESPONSE
    mock_api.send_hex_command = Mock(return_value=REAL_DEVICE_XML_RESPONSE)

    controller.fetch_status()
    controller.state.general.i_see_sensor = False
    controller.state.general.wide_vane_adjustment = True

    state = controller.set_remote_lock(RemoteLock.PowerLocked)

    mock_api.send_hex_command.assert_called_once_with("fc410130100140020000090000000000010000ac4144")
    assert state.general.remote_lock == RemoteLock.PowerLocked
    assert state.general.i_see_sensor is False
    assert state.general.wide_vane_adjustment is True


@pytest.mark.parametrize(
    "data_hex, mode, temperature",
    [
        ("fc410130100700000077", SetRemoteTemperature.Mode.UseInternal, None),
        ("fc4101301007000aaac3", SetRemoteTemperature.Mode.UseInternal, 21),
        ("fc41013010070104b6bc", SetRemoteTemperature.Mode.RemoteTemp, 27),
        ("fc41013010070110c79f", SetRemoteTemperature.Mode.RemoteTemp, 35.5),
    ],
)
def test_remote_temperature(data_hex, mode, temperature):
    command = SetRemoteTemperature(mode=mode, remote_temperature=temperature).generate_command()
    assert command.hex() == data_hex
