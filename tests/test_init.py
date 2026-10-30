"""Smoke tests with a fake ADB panel."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nspanel_pro.const import DOMAIN

COMMANDS: list[str] = []
PREFS = (
    "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
    '    <string name="mqtt-username">nspanel</string>\n'
    '    <boolean name="active" value="false" />\n'
    '    <string name="mqtt-client-id">nspanelpro</string>\n</map>'
)


class FakeAdb:
    def __init__(self, hass, host, port):
        self.hass, self.host, self.port = hass, host, port

    async def async_connect(self, auth_timeout=1.0):
        return None

    async def async_close(self):
        return None

    async def async_shell(self, command, timeout=30):
        COMMANDS.append(command)
        if "getprop ro.serialno" in command:
            return "S=ABCDEF123456\nM=NSPanel Pro\nFW=1.0\nA=8.1.0\nR=0\nVC=2026.10.1-minimal\nVT=2.3.4\nVW=120.0.1"
        if "mWakefulness" in command:
            return "W=Awake\nB=135\nU=3600.5\nIP=192.168.1.87\nC=null\nP=immersive.full=*\nF=io.homeassistant.companion.android.minimal\nPX=27.00"
        if "getevent" in command:
            return "0003 0019 0000001a\n0000 0000 00000000\n0003 0019 00000020\n0003 0019 000001f4\n0003 0019 0000001c"
        if command.startswith("su 0 cat"):
            return PREFS
        if "grep mqtt-username" in command:
            return '<string name="mqtt-username">nspanel</string>'
        return ""

    async def async_shell_nowait(self, command):
        COMMANDS.append(command)

    async def async_push(self, local, device):
        COMMANDS.append(f"push {local} {device}")


async def test_flow_and_setup(hass: HomeAssistant):
    with patch("custom_components.nspanel_pro.config_flow.NSPanelAdb", FakeAdb), patch(
        "custom_components.nspanel_pro.NSPanelAdb", FakeAdb
    ), patch("custom_components.nspanel_pro.panel.asyncio.sleep") as sleep:
        sleep.return_value = None
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.87", CONF_NAME: "NSPanel Pro", CONF_PORT: 5555, "provision": True, "dashboard_path": "nspanel-pro/home"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY, result
        await hass.async_block_till_done()
        entry = result["result"]
        assert entry.unique_id
        assert "provision" not in entry.data
        states = sorted(s.entity_id + "=" + s.state for s in hass.states.async_all() if "nspanel" in s.entity_id)
        print("\n".join(states))
        assert len(states) >= 20
        panel = entry.runtime_data
        assert panel.last_provision == "ok", panel.last_provision
        written = [c for c in COMMANDS if "base64 -d" in c]
        assert written
        import base64, re
        xml = base64.b64decode(re.search(r"echo (\S+) \| base64", written[0]).group(1)).decode()
        print(xml)
        assert 'name="mqtt-username">nspanel<' in xml
        assert "nspanelpro-123456" in xml

        # switch / number / time / button
        sw = [s.entity_id for s in hass.states.async_all("switch")]
        num = [s.entity_id for s in hass.states.async_all("number")]
        btn = [s.entity_id for s in hass.states.async_all("button")]
        tm = [s.entity_id for s in hass.states.async_all("time")]
        print(sw, num, btn, tm)
        COMMANDS.clear()
        for e in sw:
            await hass.services.async_call("switch", "turn_on", {"entity_id": e}, blocking=True)
        for e in num:
            await hass.services.async_call("number", "set_value", {"entity_id": e, "value": 30}, blocking=True)
        await hass.services.async_call("time", "set_value", {"entity_id": tm[0], "time": "04:15:00"}, blocking=True)
        for e in btn:
            if "provision" in e:
                continue
            await hass.services.async_call("button", "press", {"entity_id": e}, blocking=True)
        resp = await hass.services.async_call(DOMAIN, "shell", {"command": "echo hi"}, blocking=True, return_response=True)
        print(resp)
        await hass.async_block_till_done()
        print("\n".join(COMMANDS[:40]))
        assert hass.states.get(tm[0]).state == "04:15:00"

        # proximity
        assert hass.states.get("sensor.nspanel_pro_proximity_sensor").state == "27.0"
        await hass.services.async_call("button", "press", {"entity_id": "button.nspanel_pro_measure_proximity_10_s"}, blocking=True)
        await hass.async_block_till_done()
        peak = hass.states.get("sensor.nspanel_pro_proximity_peak")
        print(peak)
        assert peak.state == "500.0"
        assert peak.attributes["idle"] == 28.0
        COMMANDS.clear()
        await hass.services.async_call("number", "set_value", {"entity_id": "number.nspanel_pro_proximity_threshold", "value": 250}, blocking=True)
        written = [c for c in COMMANDS if "base64 -d" in c]
        xml = base64.b64decode(re.search(r"echo (\S+) \| base64", written[0]).group(1)).decode()
        assert '<int name="proximity-sensor-threshold" value="250" />' in xml

        # options flow
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"dashboard_path": "/lovelace/0", "mqtt_port": 1883, "companion_package": "io.homeassistant.companion.android.minimal", "install_companion": True, "install_tools": True})
        assert result["type"] is FlowResultType.CREATE_ENTRY, result
        await hass.async_block_till_done()
        assert entry.runtime_data.dashboard == "lovelace/0"
        assert await hass.config_entries.async_unload(entry.entry_id)
