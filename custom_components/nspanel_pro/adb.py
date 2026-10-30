"""Small async ADB client for NSPanel Pro (uses adb-shell, same key as Android TV)."""

from __future__ import annotations

import asyncio
import logging
import os

from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

_LOGGER = logging.getLogger(__name__)

_SIGNER: PythonRSASigner | None = None
_SIGNER_LOCK = asyncio.Lock()


class AdbError(Exception):
    """ADB connection or command failed."""


async def async_get_signer(hass: HomeAssistant) -> PythonRSASigner:
    """Return an RSA signer.

    The key of the built-in Android TV integration is reused when it exists, so a
    panel that already trusts Home Assistant does not ask for permission again.
    """
    global _SIGNER  # noqa: PLW0603
    async with _SIGNER_LOCK:
        if _SIGNER is not None:
            return _SIGNER

        def _load() -> PythonRSASigner:
            shared = hass.config.path(STORAGE_DIR, "androidtv_adbkey")
            own = hass.config.path(STORAGE_DIR, "nspanel_pro_adbkey")
            path = shared if os.path.isfile(shared) else own
            if not os.path.isfile(path):
                keygen(path)
            with open(path, encoding="utf-8") as priv_file:
                priv = priv_file.read()
            pub = ""
            if os.path.isfile(path + ".pub"):
                with open(path + ".pub", encoding="utf-8") as pub_file:
                    pub = pub_file.read()
            return PythonRSASigner(pub, priv)

        _SIGNER = await hass.async_add_executor_job(_load)
        return _SIGNER


class NSPanelAdb:
    """Serialised ADB access to one panel."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self._device: AdbDeviceTcpAsync | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._device is not None and self._device.available

    async def _connect(self, auth_timeout: float) -> None:
        if self.connected:
            return
        signer = await async_get_signer(self.hass)
        device = AdbDeviceTcpAsync(self.host, self.port, default_transport_timeout_s=9.0)
        try:
            ok = await device.connect(
                rsa_keys=[signer], auth_timeout_s=auth_timeout, read_timeout_s=10
            )
        except Exception as err:  # noqa: BLE001 - adb-shell raises many types
            await self._safe_close(device)
            raise AdbError(f"Cannot connect to {self.host}:{self.port}: {err}") from err
        if not ok:
            await self._safe_close(device)
            raise AdbError(f"ADB authentication failed for {self.host}")
        self._device = device

    async def async_connect(self, auth_timeout: float = 1.0) -> None:
        """Connect (auth_timeout > 1 waits for the user to accept the key)."""
        async with self._lock:
            await self._connect(auth_timeout)

    @staticmethod
    async def _safe_close(device: AdbDeviceTcpAsync | None) -> None:
        if device is None:
            return
        try:
            await device.close()
        except Exception:  # noqa: BLE001
            pass

    async def async_close(self) -> None:
        async with self._lock:
            await self._safe_close(self._device)
            self._device = None

    async def async_shell(self, command: str, timeout: float = 30) -> str:
        """Run a shell command and return its output (reconnects once on failure)."""
        async with self._lock:
            for attempt in (1, 2):
                try:
                    await self._connect(1.0)
                    assert self._device is not None
                    out = await self._device.shell(
                        command, read_timeout_s=timeout, timeout_s=timeout + 5
                    )
                    return (out or "").strip() if isinstance(out, str) else str(out)
                except AdbError:
                    raise
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("ADB shell failed (attempt %s): %s", attempt, err)
                    await self._safe_close(self._device)
                    self._device = None
                    if attempt == 2:
                        raise AdbError(f"Command failed on {self.host}: {err}") from err
        return ""

    async def async_shell_nowait(self, command: str) -> None:
        """Fire a command that drops the connection (e.g. reboot)."""
        try:
            await self.async_shell(command, timeout=5)
        except AdbError:
            pass
        await self.async_close()

    async def async_push(self, local_path: str, device_path: str) -> None:
        async with self._lock:
            await self._connect(1.0)
            assert self._device is not None
            try:
                await self._device.push(local_path, device_path, read_timeout_s=120)
            except Exception as err:  # noqa: BLE001
                await self._safe_close(self._device)
                self._device = None
                raise AdbError(f"Push failed: {err}") from err
