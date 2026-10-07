from PySide6.QtCore import Qt

from openpw2.client import ConnectionConfig
from openpw2.gui import settings
from openpw2.gui.window import Window


def test_demo_controls_tx_interlock_and_shutdown(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "prefs.json")
    window = Window(demo=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.state.get("connected") is True)
    qtbot.waitUntil(lambda: not window.busy)
    operate = next(b for b, n, a in window.buttons if n == "operate" and a["value"])
    qtbot.mouseClick(operate, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.state.get("operate") is True and not window.busy)
    qtbot.mouseClick(window.demo_tx, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.state.get("tx") is True)
    assert "≈" in window.power_value.text()
    assert all(not b.isEnabled() for b, n, a in window.buttons if n in ("antenna", "input", "tune"))
    assert "28 °C" in window.intake_label.text()
    qtbot.mouseClick(window.demo_tx, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.state.get("tx") is False)
    tune = next(b for b, n, a in window.buttons if n == "tune")
    qtbot.mouseClick(tune, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.state.get("tuning") is True)
    qtbot.waitUntil(lambda: window.state.get("atu") == "on" and not window.busy, timeout=4000)
    window.close()
    assert not window.bridge.isRunning()


def test_preferences_never_store_password(tmp_path):
    path = tmp_path / "prefs.json"
    config = ConnectionConfig("example.test", "testuser", "never-on-disk", mains_v=230)
    settings.save(config, path)
    assert "never-on-disk" not in path.read_text() and "password" not in path.read_text()
    assert settings.load(path)["host"] == "example.test"


def test_real_gui_login_control_confirmation_and_disconnect(qtbot, tmp_path, monkeypatch):
    """Real Client and Qt bridge, using only a localhost synthetic amplifier."""
    import asyncio

    from .fake_pw2 import fake_pw2

    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "prefs.json")
    window = Window()
    qtbot.addWidget(window)
    window.show()
    context = fake_pw2()
    peer = asyncio.run_coroutine_threadsafe(context.__aenter__(), window.bridge.loop).result(3)
    try:
        window.host_edit.setText("127.0.0.1")
        window.port_edit.setValue(peer.port)
        window.user_edit.setText("testuser")
        window.password_edit.setText("testpass")
        window.mains_edit.setCurrentIndex(1)
        window.tabs.setCurrentIndex(1)
        qtbot.mouseClick(window.form_connect, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.state.get("connected") is True and not window.busy)
        assert window.connection_badge.text() == "CONNECTED"
        assert "14.210" in window.frequency_label.text()
        assert [p.channel for p in peer.frames] == [0, 0]
        operate = next(b for b, n, a in window.buttons if n == "operate" and a["value"])
        qtbot.mouseClick(operate, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.state.get("operate") is True and not window.busy)
        assert operate.isChecked()
        assert peer.frames[-1].body == bytes.fromhex("010002")
        qtbot.mouseClick(window.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not window.state.get("connected") and not window.busy)
        assert not any(p.channel == 4 for p in peer.frames)
        assert "testpass" not in (tmp_path / "prefs.json").read_text()
    finally:
        asyncio.run_coroutine_threadsafe(context.__aexit__(None, None, None), window.bridge.loop).result(3)
        window.close()
    assert not window.bridge.isRunning()
