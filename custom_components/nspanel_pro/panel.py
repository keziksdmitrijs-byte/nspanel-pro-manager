"""NSPanel Pro device logic: status polling, settings, actions and provisioning."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import os
import re
from typing import Any
from xml.etree import ElementTree as ET

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import STORAGE_DIR, Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .adb import AdbError, NSPanelAdb
from .const import (
    COMPANION_APK_URL,
    CONF_COMPANION_PACKAGE,
    CONF_DASHBOARD,
    CONF_INSTALL_COMPANION,
    CONF_INSTALL_TOOLS,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    DEFAULT_COMPANION_PACKAGE,
    DEFAULT_DASHBOARD,
    DEFAULT_MQTT_PORT,
    DEFAULT_SETTINGS,
    DOMAIN,
    EWELINK_BACK_SERVICE,
    PROXIMITY_INPUT,
    PROXIMITY_MEASURE_SECONDS,
    SET_BRIGHTNESS,
    SET_DIM_BRIGHTNESS,
    SET_NIGHTLY_REBOOT,
    SET_PROXIMITY_THRESHOLD,
    SET_REBOOT_TIME,
    SET_SCREENSAVER,
    SET_SCREENSAVER_TIMEOUT,
    SET_SYSTEM_CONTROLS,
    TOOLS_ADMIN_RECEIVER,
    TOOLS_PACKAGE,
    TOOLS_PREFS,
    TOOLS_RELEASES_API,
    TOOLS_TIMEOUTS_MS,
    UPDATE_INTERVAL,
    VERSIONS_EVERY,
)

_LOGGER = logging.getLogger(__name__)

STATUS_CMD = (
    'echo "W=$(dumpsys power | grep -m1 mWakefulness= | cut -d= -f2)";'
    'echo "B=$(settings get system screen_brightness)";'
    "echo \"U=$(cut -d' ' -f1 /proc/uptime)\";"
    "echo \"IP=$(ip -4 addr show wlan0 2>/dev/null | grep -o 'inet [0-9.]*' | cut -d' ' -f2)\";"
    'echo "C=$(settings get secure enabled_accessibility_services)";'
    'echo "P=$(settings get global policy_control)";'
    "echo \"F=$(dumpsys window windows | grep -m1 mCurrentFocus | grep -o 'u0 [^/ ]*' | cut -d' ' -f2)\";"
    "echo \"PX=$(dumpsys sensorservice | grep -A1 'Proximity sensor: last' | tail -1 | sed -E 's/.*[)] ([0-9.]+),.*/\\1/')\""
)


MSG = {
    "en": {
        "no_root": "Root (su) is not available — NSPanel Pro Tools settings are skipped.",
        "companion": "Home Assistant Companion installed",
        "tools": "NSPanel Pro Tools installed",
        "tools_cfg": "NSPanel Pro Tools configured (wake on wave, dimming, autostart of Home Assistant, MQTT broker address)",
        "mqtt": "Enter the MQTT username and password in NSPanel Pro Tools → integration → MQTT → Setup and switch it on.",
        "android": "Android settings applied (screen always on, clean screen, brightness)",
        "webview": "System WebView {v} is old — update the panel firmware, otherwise the dashboard may not load.",
        "login": "On the panel log in to Home Assistant (if asked) and set the dashboard as default for this device.",
        "error": "Error: {e}",
        "done": "Done:",
        "todo": "Left to do:",
        "title": "NSPanel Pro setup",
    },
    "ru": {
        "no_root": "Root (su) недоступен — настройки NSPanel Pro Tools пропущены.",
        "companion": "Установлен Home Assistant Companion",
        "tools": "Установлен NSPanel Pro Tools",
        "tools_cfg": "Настроен NSPanel Pro Tools (пробуждение взмахом, приглушение, автозапуск Home Assistant, адрес MQTT-брокера)",
        "mqtt": "Введите логин и пароль MQTT в NSPanel Pro Tools → integration → MQTT → Setup и включите Enabled.",
        "android": "Применены настройки Android (экран всегда включён, чистый экран, яркость)",
        "webview": "Системный WebView {v} устарел — обновите прошивку панели, иначе дашборд может не открыться.",
        "login": "На панели войдите в Home Assistant (если попросит) и сделайте дашборд основным для этого устройства.",
        "error": "Ошибка: {e}",
        "done": "Сделано:",
        "todo": "Осталось:",
        "title": "Настройка NSPanel Pro",
    },
    "lv": {
        "no_root": "Root (su) nav pieejams — NSPanel Pro Tools iestatījumi izlaisti.",
        "companion": "Instalēts Home Assistant Companion",
        "tools": "Instalēts NSPanel Pro Tools",
        "tools_cfg": "Iestatīts NSPanel Pro Tools (pamošanās ar roku, aptumšošana, Home Assistant automātiska palaišana, MQTT brokera adrese)",
        "mqtt": "Ievadiet MQTT lietotāju un paroli NSPanel Pro Tools → integration → MQTT → Setup un ieslēdziet Enabled.",
        "android": "Piemēroti Android iestatījumi (ekrāns vienmēr ieslēgts, tīrs ekrāns, spilgtums)",
        "webview": "Sistēmas WebView {v} ir novecojis — atjauniniet paneļa programmaparatūru.",
        "login": "Panelī piesakieties Home Assistant (ja prasa) un iestatiet informācijas paneli kā noklusēto.",
        "error": "Kļūda: {e}",
        "done": "Izdarīts:",
        "todo": "Vēl jāizdara:",
        "title": "NSPanel Pro iestatīšana",
    },
}


def _parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


@dataclass
class PanelInfo:
    """Static information about a panel."""

    serial: str = ""
    model: str = ""
    firmware: str = ""
    android: str = ""
    root: bool = False
    companion: str | None = None
    tools: str | None = None
    webview: str | None = None


@dataclass
class PanelStatus:
    """Polled status of a panel."""

    online: bool = False
    awake: bool | None = None
    brightness: int | None = None
    boot_time: datetime | None = None
    ip: str | None = None
    circle: bool | None = None
    immersive: bool | None = None
    foreground: str | None = None
    proximity: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class NSPanel:
    """One NSPanel Pro controlled over ADB."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, adb: NSPanelAdb) -> None:
        self.hass = hass
        self.entry = entry
        self.adb = adb
        self.info = PanelInfo()
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._unsub_reboot = None
        self._was_online = True
        self._updates = 0
        self.provisioning = False
        self.last_provision: str | None = None
        self.measuring = False
        self.proximity_measure: dict[str, Any] | None = None
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {adb.host}",
            update_interval=UPDATE_INTERVAL,
            update_method=self._async_update,
        )

    def _t(self, key: str, **kwargs: Any) -> str:
        lang = (self.hass.config.language or "en")[:2]
        text = MSG.get(lang, MSG["en"]).get(key) or MSG["en"][key]
        return text.format(**kwargs) if kwargs else text

    # ------------------------------------------------------------------ options
    @property
    def companion_package(self) -> str:
        return self.entry.options.get(CONF_COMPANION_PACKAGE, DEFAULT_COMPANION_PACKAGE)

    @property
    def dashboard(self) -> str:
        path = self.entry.options.get(CONF_DASHBOARD, DEFAULT_DASHBOARD) or ""
        return path.strip("/")

    @property
    def title(self) -> str:
        return self.entry.title

    # ----------------------------------------------------------------- lifecycle
    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.settings.update(stored)
        await self.async_refresh_info()
        self._schedule_reboot()

    async def async_unload(self) -> None:
        if self._unsub_reboot:
            self._unsub_reboot()
            self._unsub_reboot = None
        await self.adb.async_close()

    async def async_refresh_info(self) -> None:
        """Read static device information."""
        out = await self.adb.async_shell(
            'echo "S=$(getprop ro.serialno)";'
            'echo "M=$(getprop ro.product.model)";'
            'echo "FW=$(getprop ro.build.display.id)";'
            'echo "A=$(getprop ro.build.version.release)";'
            'echo "R=$(su 0 id -u 2>/dev/null)";'
            + self._versions_cmd()
        )
        kv = _parse_kv(out)
        self.info.serial = kv.get("S", "")
        self.info.model = kv.get("M", "")
        self.info.firmware = kv.get("FW", "")
        self.info.android = kv.get("A", "")
        self.info.root = kv.get("R", "") == "0"
        self._apply_versions(kv)

    def _versions_cmd(self) -> str:
        def ver(pkg: str, key: str) -> str:
            return (
                f'echo "{key}=$(dumpsys package {pkg} | grep -m1 versionName | cut -d= -f2)";'
            )

        return (
            ver(self.companion_package, "VC")
            + ver(TOOLS_PACKAGE, "VT")
            + ver("com.android.webview", "VW")
        )

    def _apply_versions(self, kv: dict[str, str]) -> None:
        self.info.companion = kv.get("VC") or None
        self.info.tools = kv.get("VT") or None
        self.info.webview = kv.get("VW") or None

    async def _async_update(self) -> PanelStatus:
        self._updates += 1
        cmd = STATUS_CMD
        if self._updates % VERSIONS_EVERY == 0:
            cmd += ";" + self._versions_cmd()
        try:
            out = await self.adb.async_shell(cmd, timeout=15)
        except AdbError as err:
            self._was_online = False
            raise UpdateFailed(str(err)) from err
        kv = _parse_kv(out)
        if "VC" in kv:
            self._apply_versions(kv)
        status = PanelStatus(online=True)
        wake = kv.get("W", "")
        status.awake = wake == "Awake" if wake else None
        try:
            status.brightness = int(kv.get("B", ""))
        except ValueError:
            status.brightness = None
        try:
            uptime = float(kv.get("U", ""))
            boot = dt_util.utcnow() - timedelta(seconds=uptime)
            status.boot_time = boot.replace(second=0, microsecond=0)
        except ValueError:
            status.boot_time = None
        status.ip = kv.get("IP") or None
        status.circle = "BackButtonService" in kv.get("C", "")
        status.immersive = "immersive" in kv.get("P", "")
        status.foreground = kv.get("F") or None
        try:
            status.proximity = float(kv.get("PX", ""))
        except ValueError:
            status.proximity = None

        if not self._was_online:
            # Panel came back (e.g. after a reboot): re-apply our settings
            self._was_online = True
            self.hass.async_create_background_task(
                self._async_after_reconnect(), f"{DOMAIN} reconnect {self.adb.host}"
            )
        return status

    async def _async_after_reconnect(self) -> None:
        await asyncio.sleep(20)
        try:
            await self.async_apply_settings()
        except AdbError as err:
            _LOGGER.debug("Could not re-apply settings: %s", err)

    # ------------------------------------------------------------------ settings
    async def async_set(self, key: str, value: Any) -> None:
        """Change a persistent setting and apply it to the panel."""
        self.settings[key] = value
        await self._store.async_save(self.settings)
        if key == SET_SYSTEM_CONTROLS:
            await self.async_apply_system_controls()
        elif key == SET_BRIGHTNESS:
            await self.adb.async_shell(self._brightness_cmd())
            await self.async_write_tools_prefs(restart=True)
        elif key in (SET_DIM_BRIGHTNESS, SET_SCREENSAVER, SET_SCREENSAVER_TIMEOUT, SET_PROXIMITY_THRESHOLD):
            await self.async_write_tools_prefs(restart=True)
        elif key in (SET_REBOOT_TIME, SET_NIGHTLY_REBOOT):
            self._schedule_reboot()
        self.coordinator.async_update_listeners()

    def _brightness_cmd(self) -> str:
        value = round(int(self.settings[SET_BRIGHTNESS]) * 255 / 100)
        return (
            "settings put system screen_brightness_mode 0;"
            f"settings put system screen_brightness {max(1, min(255, value))}"
        )

    def _system_controls_cmd(self) -> str:
        if self.settings[SET_SYSTEM_CONTROLS]:
            return (
                "settings put global policy_control null;"
                f"settings put secure enabled_accessibility_services {EWELINK_BACK_SERVICE};"
                "settings put secure accessibility_enabled 1"
            )
        return (
            "settings put global policy_control immersive.full=*;"
            "settings delete secure enabled_accessibility_services;"
            "settings put secure accessibility_enabled 0"
        )

    async def async_apply_system_controls(self) -> None:
        await self.adb.async_shell(self._system_controls_cmd())

    async def async_apply_settings(self) -> None:
        """Apply all Android-side settings."""
        await self.adb.async_shell(
            "settings put system screen_off_timeout 2147483647;"
            + self._brightness_cmd()
            + ";"
            + self._system_controls_cmd()
        )

    # ------------------------------------------------------------------- actions
    async def async_reboot(self) -> None:
        cmd = "su 0 reboot" if self.info.root else "reboot"
        await self.adb.async_shell_nowait(cmd)
        self._was_online = False
        self.hass.async_create_background_task(
            self._async_open_after_reboot(), f"{DOMAIN} after reboot {self.adb.host}"
        )

    async def _async_open_after_reboot(self) -> None:
        # The panel is usually back after 60-90 s; NSPanel Pro Tools starts the
        # Home Assistant app itself, this is only a fallback.
        for _ in range(12):
            await asyncio.sleep(15)
            try:
                await self.adb.async_shell("echo ok", timeout=5)
            except AdbError:
                continue
            await asyncio.sleep(25)
            try:
                await self.async_apply_settings()
                await self.async_open_dashboard()
            except AdbError:
                pass
            await self.coordinator.async_request_refresh()
            return

    async def async_open_dashboard(self) -> None:
        pkg = self.companion_package
        await self.adb.async_shell(
            "input keyevent KEYCODE_WAKEUP;"
            f'am start -a android.intent.action.VIEW -d "homeassistant://navigate/{self.dashboard}" {pkg}'
        )

    async def async_restart_app(self) -> None:
        await self.adb.async_shell(f"am force-stop {self.companion_package}")
        await asyncio.sleep(2)
        await self.async_open_dashboard()

    async def async_screen(self, on: bool) -> None:
        key = "KEYCODE_WAKEUP" if on else "KEYCODE_SLEEP"
        await self.adb.async_shell(f"input keyevent {key}")
        await self.coordinator.async_request_refresh()

    async def async_open_tools(self) -> None:
        await self.adb.async_shell(
            "input keyevent KEYCODE_WAKEUP;"
            f"monkey -p {TOOLS_PACKAGE} -c android.intent.category.LAUNCHER 1"
        )

    async def async_measure_proximity(self, seconds: int = PROXIMITY_MEASURE_SECONDS) -> None:
        """Record raw proximity values for a few seconds (wave a hand meanwhile)."""
        if self.measuring:
            return
        self.measuring = True
        self.coordinator.async_update_listeners()
        values: list[float] = []
        try:
            if self.info.root:
                out = await self.adb.async_shell(
                    f"su 0 timeout {seconds} getevent {PROXIMITY_INPUT} 2>/dev/null; true",
                    timeout=seconds + 15,
                )
                # lines: "0003 0019 00000021" (EV_ABS ABS_DISTANCE value)
                for match in re.finditer(r"0003 0019 ([0-9a-f]{8})", out):
                    values.append(float(int(match.group(1), 16)))
            else:
                for _ in range(seconds):
                    out = await self.adb.async_shell(
                        "dumpsys sensorservice | grep -A10 'Proximity sensor: last'", timeout=10
                    )
                    values += [float(v) for v in re.findall(r"\) ([0-9.]+),", out)]
                    await asyncio.sleep(1)
        except AdbError as err:
            _LOGGER.warning("Proximity measurement on %s failed: %s", self.adb.host, err)
        finally:
            self.measuring = False
        if values:
            idle = sorted(values)[(len(values) - 1) // 2]
            self.proximity_measure = {
                "max": max(values),
                "min": min(values),
                "idle": idle,
                "samples": len(values),
                # a hand gives a clear peak well above the background noise
                "hand_detected": max(values) >= idle * 2 + 20,
                # halfway between background noise and the hand
                "suggested_threshold": round(idle + (max(values) - idle) / 2)
                if max(values) >= idle * 2 + 20
                else None,
                "measured_at": dt_util.utcnow().isoformat(timespec="seconds"),
            }
        self.coordinator.async_update_listeners()

    # ------------------------------------------------------------ nightly reboot
    @callback
    def _schedule_reboot(self) -> None:
        if self._unsub_reboot:
            self._unsub_reboot()
            self._unsub_reboot = None
        if not self.settings.get(SET_NIGHTLY_REBOOT):
            return
        try:
            hour, minute, second = (int(x) for x in str(self.settings[SET_REBOOT_TIME]).split(":"))
        except ValueError:
            hour, minute, second = 3, 30, 0

        async def _fire(_now: datetime) -> None:
            _LOGGER.info("Nightly reboot of %s", self.adb.host)
            try:
                await self.async_reboot()
            except AdbError as err:
                _LOGGER.warning("Nightly reboot of %s failed: %s", self.adb.host, err)

        self._unsub_reboot = async_track_time_change(
            self.hass, _fire, hour=hour, minute=minute, second=second
        )

    # ------------------------------------------------------- NSPanel Pro Tools
    def _tools_timeout_ms(self) -> int:
        if not self.settings.get(SET_SCREENSAVER):
            return TOOLS_TIMEOUTS_MS[-1]
        wanted = int(self.settings[SET_SCREENSAVER_TIMEOUT]) * 1000
        return min(TOOLS_TIMEOUTS_MS, key=lambda x: abs(x - wanted))

    async def _mqtt_host(self) -> str:
        host = self.entry.options.get(CONF_MQTT_HOST)
        if host:
            return host
        try:
            from homeassistant.components.network import async_get_source_ip

            return await async_get_source_ip(self.hass)
        except Exception:  # noqa: BLE001
            return "homeassistant.local"

    async def async_write_tools_prefs(self, restart: bool) -> bool:
        """Merge our settings into NSPanel Pro Tools preferences (needs root)."""
        if not self.info.root or not self.info.tools:
            return False
        current = await self.adb.async_shell(f"su 0 cat {TOOLS_PREFS} 2>/dev/null")
        existing: dict[str, ET.Element] = {}
        if current.startswith("<?xml") or "<map" in current:
            try:
                root = ET.fromstring(current[current.find("<map") :])
                for el in root:
                    if el.get("name"):
                        existing[el.get("name")] = el
            except ET.ParseError:
                existing = {}

        serial_tail = re.sub(r"[^A-Za-z0-9]", "", self.info.serial)[-6:].lower() or "panel"
        managed: dict[str, tuple[str, Any]] = {
            "active": ("boolean", True),
            "wake-on-wave": ("boolean", True),
            "wake-on-connerror": ("boolean", True),
            "screen-off-mode": ("string", "screen-dim-custom"),
            "screen-off-timeout": ("string", str(self._tools_timeout_ms())),
            "brightness": ("int", int(self.settings[SET_BRIGHTNESS])),
            "brightness-dim-custom": ("int", int(self.settings[SET_DIM_BRIGHTNESS])),
            "resume-on-boot": ("boolean", True),
            "launch-app": ("string", self.companion_package),
            "launch-app-wait": ("boolean", True),
            "mqtt-host": ("string", await self._mqtt_host()),
            "mqtt-host-port": ("string", str(self.entry.options.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT))),
            "mqtt-publish": ("string", "proximity|wake-up|sleep"),
            "mqtt-command": ("boolean", True),
            "mqtt-ha-integration": ("boolean", True),
            "mqtt-ha-topic-prefix": ("string", "homeassistant"),
            "proximity-sensor-threshold": ("int", int(self.settings.get(SET_PROXIMITY_THRESHOLD) or 0)),
        }
        if "mqtt-client-id" not in existing or existing["mqtt-client-id"].text in (None, "", "nspanelpro"):
            managed["mqtt-client-id"] = ("string", f"nspanelpro-{serial_tail}")

        root = ET.Element("map")
        for name, el in existing.items():
            if name not in managed:
                root.append(el)
        for name, (kind, value) in managed.items():
            if kind == "string":
                el = ET.SubElement(root, "string", name=name)
                el.text = str(value)
            else:
                ET.SubElement(
                    root, kind, name=name, value=str(value).lower() if kind == "boolean" else str(value)
                )
        ET.indent(root, space="    ")
        xml = "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n" + ET.tostring(
            root, encoding="unicode"
        )
        payload = base64.b64encode(xml.encode()).decode()
        prefs_dir = os.path.dirname(TOOLS_PREFS)
        await self.adb.async_shell(f"am force-stop {TOOLS_PACKAGE}")
        await self.adb.async_shell(
            f"echo {payload} | base64 -d > /data/local/tmp/nsp_tools.xml;"
            f"su 0 sh -c 'mkdir -p {prefs_dir};"
            f"cp /data/local/tmp/nsp_tools.xml {TOOLS_PREFS};"
            f"U=$(stat -c %u /data/data/{TOOLS_PACKAGE});"
            f"chown $U:$U {prefs_dir} {TOOLS_PREFS};"
            f"chmod 660 {TOOLS_PREFS}';"
            "rm /data/local/tmp/nsp_tools.xml"
        )
        if restart:
            await self.adb.async_shell(
                f"monkey -p {TOOLS_PACKAGE} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
            )
            await asyncio.sleep(4)
            await self.async_open_dashboard()
        return True

    # --------------------------------------------------------------- provisioning
    async def _download_on_panel(self, url: str, dest: str, min_size: int) -> bool:
        out = await self.adb.async_shell(
            f"cd /data/local/tmp && curl -sSL -o {dest} '{url}' 2>&1; stat -c %s {dest} 2>/dev/null",
            timeout=600,
        )
        sizes = re.findall(r"^\d+$", out, re.M)
        return bool(sizes) and int(sizes[-1]) >= min_size

    async def _download_via_ha(self, url: str, dest: str) -> None:
        session = async_get_clientsession(self.hass)
        local = self.hass.config.path(STORAGE_DIR, f"nspanel_pro_{os.path.basename(dest)}")
        async with session.get(url, timeout=600) as resp:
            resp.raise_for_status()
            data = await resp.read()

        def _write() -> None:
            with open(local, "wb") as file:
                file.write(data)

        await self.hass.async_add_executor_job(_write)
        try:
            await self.adb.async_push(local, f"/data/local/tmp/{dest}")
        finally:
            await self.hass.async_add_executor_job(os.remove, local)

    async def _install(self, url: str, dest: str, min_size: int) -> str:
        if not await self._download_on_panel(url, dest, min_size):
            await self._download_via_ha(url, dest)
        out = await self.adb.async_shell(
            f"pm install -r -g /data/local/tmp/{dest} 2>&1; rm -f /data/local/tmp/{dest}", timeout=300
        )
        if "Success" not in out:
            raise AdbError(f"Install failed: {out[-200:]}")
        return out

    async def _tools_url(self) -> str:
        session = async_get_clientsession(self.hass)
        async with session.get(TOOLS_RELEASES_API, timeout=30) as resp:
            resp.raise_for_status()
            releases = await resp.json()
        for rel in releases:
            for asset in rel.get("assets", []):
                name = asset.get("name", "")
                if name.endswith("-release.apk") and "system" not in name:
                    return asset["browser_download_url"]
        raise AdbError("No NSPanel Pro Tools release found")

    async def async_provision(self) -> None:
        """Set up a panel to work like the reference one."""
        if self.provisioning:
            return
        self.provisioning = True
        self.coordinator.async_update_listeners()
        done: list[str] = []
        todo: list[str] = []
        try:
            await self.async_refresh_info()
            if not self.info.root:
                todo.append(self._t("no_root"))

            if self.entry.options.get(CONF_INSTALL_COMPANION, True) and not self.info.companion:
                flavor = "app-minimal" if self.companion_package.endswith(".minimal") else "app-full"
                await self._install(COMPANION_APK_URL.format(flavor=flavor), "ha.apk", 5_000_000)
                done.append(self._t("companion"))
            if self.entry.options.get(CONF_INSTALL_TOOLS, True) and not self.info.tools:
                await self._install(await self._tools_url(), "tools.apk", 500_000)
                done.append(self._t("tools"))
            await self.async_refresh_info()

            if self.info.tools:
                pkg = TOOLS_PACKAGE
                await self.adb.async_shell(
                    f"dumpsys deviceidle whitelist +{pkg};"
                    f"appops set {pkg} SYSTEM_ALERT_WINDOW allow;"
                    f"appops set {pkg} WRITE_SETTINGS allow;"
                    f"pm grant {pkg} android.permission.READ_EXTERNAL_STORAGE 2>/dev/null;"
                    f"dpm set-active-admin --user 0 {TOOLS_ADMIN_RECEIVER} 2>/dev/null;"
                    f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
                )
                await asyncio.sleep(5)
                if await self.async_write_tools_prefs(restart=False):
                    done.append(self._t("tools_cfg"))
                prefs = await self.adb.async_shell(f"su 0 grep mqtt-username {TOOLS_PREFS} 2>/dev/null")
                if not re.search(r">[^<]+<", prefs):
                    todo.append(self._t("mqtt"))
                await self.adb.async_shell(
                    f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1"
                )
                await asyncio.sleep(3)

            await self.async_apply_settings()
            done.append(self._t("android"))
            if self.info.webview:
                try:
                    if int(self.info.webview.split(".")[0]) < 100:
                        todo.append(self._t("webview", v=self.info.webview))
                except ValueError:
                    pass
            await self.async_open_dashboard()
            todo.append(self._t("login"))
            self.last_provision = "ok"
        except (AdbError, Exception) as err:  # noqa: BLE001
            _LOGGER.exception("Provisioning of %s failed", self.adb.host)
            self.last_provision = f"error: {err}"
            todo.insert(0, self._t("error", e=err))
        finally:
            self.provisioning = False
            self.coordinator.async_update_listeners()
            await self.coordinator.async_request_refresh()

        message = f"**{self.title}** ({self.adb.host})\n\n"
        if done:
            message += self._t("done") + "\n" + "\n".join(f"- {x}" for x in done) + "\n\n"
        if todo:
            message += self._t("todo") + "\n" + "\n".join(f"- {x}" for x in todo)
        persistent_notification.async_create(
            self.hass, message, title=self._t("title"), notification_id=f"{DOMAIN}_{self.entry.entry_id}"
        )
