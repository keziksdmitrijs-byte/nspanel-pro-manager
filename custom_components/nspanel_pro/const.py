"""Constants for NSPanel Pro Manager."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nspanel_pro"

CONF_DASHBOARD: Final = "dashboard_path"
CONF_MQTT_HOST: Final = "mqtt_host"
CONF_MQTT_PORT: Final = "mqtt_port"
CONF_COMPANION_PACKAGE: Final = "companion_package"
CONF_INSTALL_COMPANION: Final = "install_companion"
CONF_INSTALL_TOOLS: Final = "install_tools"
CONF_PROVISION: Final = "provision"

DEFAULT_PORT: Final = 5555
DEFAULT_DASHBOARD: Final = "nspanel-pro/home"
DEFAULT_MQTT_PORT: Final = 1883
DEFAULT_COMPANION_PACKAGE: Final = "io.homeassistant.companion.android.minimal"

TOOLS_PACKAGE: Final = "com.seaky.nspanelpro.tools"
TOOLS_ADMIN_RECEIVER: Final = f"{TOOLS_PACKAGE}/.receiver.DeviceAdminReceiver"
TOOLS_PREFS: Final = (
    f"/data/data/{TOOLS_PACKAGE}/shared_prefs/{TOOLS_PACKAGE}_preferences.xml"
)
TOOLS_RELEASES_API: Final = (
    "https://api.github.com/repos/seaky/nspanel_pro_tools_apk/releases?per_page=10"
)
COMPANION_APK_URL: Final = (
    "https://github.com/home-assistant/android/releases/latest/download/"
    "{flavor}-release.apk"
)

# Floating "back" circle of the stock Sonoff app (accessibility overlay)
EWELINK_BACK_SERVICE: Final = (
    "com.eWeLinkControlPanel/"
    "com.coolkit.nspanelpro.service.accessibility.BackButtonService"
)

UPDATE_INTERVAL: Final = timedelta(seconds=30)
VERSIONS_EVERY: Final = 20  # refresh app versions every N updates

# Persistent settings (per panel) and their defaults
SET_SYSTEM_CONTROLS: Final = "system_controls"
SET_NIGHTLY_REBOOT: Final = "nightly_reboot"
SET_REBOOT_TIME: Final = "reboot_time"
SET_BRIGHTNESS: Final = "brightness"
SET_DIM_BRIGHTNESS: Final = "dim_brightness"
SET_SCREENSAVER: Final = "screensaver"
SET_SCREENSAVER_TIMEOUT: Final = "screensaver_timeout"

DEFAULT_SETTINGS: Final = {
    SET_SYSTEM_CONTROLS: False,
    SET_NIGHTLY_REBOOT: True,
    SET_REBOOT_TIME: "03:30:00",
    SET_BRIGHTNESS: 53,
    SET_DIM_BRIGHTNESS: 9,
    SET_SCREENSAVER: True,
    SET_SCREENSAVER_TIMEOUT: 60,
}

# NSPanel Pro Tools only accepts these display-sleep timeouts (ms)
TOOLS_TIMEOUTS_MS: Final = [15000, 30000, 60000, 120000, 300000, 600000, 1800000]
