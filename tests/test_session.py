import pytest

from kami.session import Session, capture_failed_message, detect, hotkey_fallback_message

OLD_CAPTURE_FAILED = (
    "Kami couldn't capture your screen. On Wayland, screen capture isn't supported yet: "
    'log in with "Ubuntu on Xorg" (or "GNOME on Xorg") to use Explain screen.'
)


def test_x11_from_session_type():
    assert detect({"XDG_SESSION_TYPE": "x11"}).kind == "x11"


def test_wayland_from_session_type():
    assert detect({"XDG_SESSION_TYPE": "wayland"}).kind == "wayland"


def test_session_type_is_trimmed_and_lowercased():
    assert detect({"XDG_SESSION_TYPE": " Wayland "}).kind == "wayland"


def test_tty_session_type_falls_through_to_display():
    assert detect({"XDG_SESSION_TYPE": "tty", "DISPLAY": ":0"}).kind == "x11"


def test_session_type_beats_the_display_variables():
    env = {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    assert detect(env).kind == "x11"


def test_falls_back_to_wayland_display():
    # WAYLAND_DISPLAY wins over DISPLAY: a Wayland session also sets DISPLAY for XWayland.
    assert detect({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}).kind == "wayland"


def test_falls_back_to_display():
    assert detect({"DISPLAY": ":0"}).kind == "x11"


def test_blank_display_variables_are_ignored():
    assert detect({"WAYLAND_DISPLAY": "  ", "DISPLAY": ""}).kind == "unknown"


def test_nothing_set_is_unknown():
    session = detect({})
    assert session == Session("unknown", "other")
    assert session.capture == "x11"      # unknown still tries grabWindow, as before
    assert session.hotkey == "pynput"


@pytest.mark.parametrize("value, desktop", [
    ("ubuntu:GNOME", "gnome"),
    ("GNOME", "gnome"),
    ("KDE", "kde"),
    ("sway", "sway"),
    ("Hyprland", "hyprland"),
    ("XFCE", "other"),
    ("", "other"),
    ("::", "other"),
])
def test_desktop_names(value, desktop):
    assert detect({"XDG_CURRENT_DESKTOP": value}).desktop == desktop


def test_desktop_missing_is_other():
    assert detect({"XDG_SESSION_TYPE": "wayland"}).desktop == "other"


def test_desktop_uses_first_known_part():
    assert detect({"XDG_CURRENT_DESKTOP": "Unity:KDE:GNOME"}).desktop == "kde"


def test_xwayland_from_qt_platform():
    session = detect({"XDG_SESSION_TYPE": "wayland"}, qt_platform="xcb")
    assert session.xwayland is True
    assert session.capture == "portal"
    assert session.hotkey == "portal"


def test_native_wayland_qt_is_not_xwayland():
    env = {"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "xcb"}
    # qt_platform is what Qt really picked, so it beats the env hint.
    assert detect(env, qt_platform="wayland").xwayland is False


def test_xwayland_from_env_when_no_qt_platform():
    env = {"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "xcb;wayland"}
    assert detect(env).xwayland is True


def test_no_qt_platform_anywhere_is_not_xwayland():
    assert detect({"XDG_SESSION_TYPE": "wayland"}).xwayland is False


def test_xwayland_only_on_wayland():
    assert detect({"XDG_SESSION_TYPE": "x11"}, qt_platform="xcb").xwayland is False
    assert detect({}, qt_platform="xcb").xwayland is False


def test_capture_and_hotkey_choices():
    x11 = detect({"XDG_SESSION_TYPE": "x11"})
    wayland = detect({"XDG_SESSION_TYPE": "wayland"})
    assert (x11.capture, x11.hotkey) == ("x11", "pynput")
    assert (wayland.capture, wayland.hotkey) == ("portal", "portal")


def test_describe_and_log_fields():
    gnome = Session("wayland", "gnome")
    assert gnome.describe() == "wayland · gnome"
    assert gnome.log_fields() == "kind=wayland desktop=gnome xwayland=no"
    xw = Session("wayland", "gnome", xwayland=True)
    assert xw.describe() == "wayland · gnome · xwayland"
    assert xw.log_fields() == "kind=wayland desktop=gnome xwayland=yes"
    assert Session("unknown", "other").describe() == "unknown · other"


def test_detect_never_raises_on_odd_values():
    env = {"XDG_SESSION_TYPE": None, "WAYLAND_DISPLAY": 3, "XDG_CURRENT_DESKTOP": b"KDE",
           "QT_QPA_PLATFORM": object()}
    assert detect(env) == Session("unknown", "other")


def test_detect_never_raises_on_a_broken_mapping():
    class Broken(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("boom")

    assert detect(Broken()) == Session("unknown", "other")


def test_capture_failed_message_wayland_keeps_old_text():
    assert capture_failed_message(Session("wayland", "gnome")) == OLD_CAPTURE_FAILED
    assert capture_failed_message(Session("wayland", "kde", xwayland=True)) == OLD_CAPTURE_FAILED


def test_capture_failed_message_x11_points_to_doctor():
    expected = "Kami couldn't capture your screen. Run `kami doctor` to see why."
    assert capture_failed_message(Session("x11", "gnome")) == expected
    assert capture_failed_message(Session("unknown", "other")) == expected


def test_hotkey_fallback_message_wayland_keeps_old_text():
    assert hotkey_fallback_message(Session("wayland", "gnome")) == (
        "Wayland session: bind a desktop shortcut to `kami toggle`."
    )


def test_hotkey_fallback_message_elsewhere_names_kami_toggle():
    assert "kami toggle" in hotkey_fallback_message(Session("x11", "other"))
