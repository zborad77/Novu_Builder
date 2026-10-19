"""Vazba zařízení ↔ firma v zóně desktop (F3.6, aktivace v F7.4).

Desktop se k core připojuje přes WireGuard. Kryptografické směrování WG váže
zdrojovou adresu tunelu na veřejný klíč peeru, takže adresa ve ``wg-nc``
(``10.50.16.0/20``), kterou nginx předá přes unix socket a vyhodnotí
``TrustedProxyMiddleware``, identifikuje enrollované zařízení. Zařízení patří
jedné firmě; s ``NC_DEVICE_BINDING=enforce`` se uživatel jiné firmy na tomto
zařízení nepřihlásí a jeho tokeny se na něm neuznají (403).

Do F7 (tabulka ``devices`` a enrollment) je registr souborový:

    {"version": 1, "devices": [
        {"deviceId": "dev-01", "wgAddress": "10.50.16.10",
         "organizationId": "org_x", "revoked": false}
    ]}

Výchozí stav je ``off``. ``enforce`` bez čitelného registru odmítne vše (fail
closed) a mimo zónu desktop ho konfigurace nepovolí.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

import structlog

from app.platform.http.client_ip import parse_ip

logger = structlog.get_logger(__name__)

BindingDecision = Literal["allow", "unknown_device", "revoked_device", "organization_mismatch", "registry_unavailable"]


@dataclass(frozen=True)
class RegisteredDevice:
    device_id: str
    wg_address: str
    organization_id: str
    revoked: bool


class DeviceRegistryError(ValueError):
    pass


def parse_registry(data: object) -> dict[str, RegisteredDevice]:
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("devices"), list):
        raise DeviceRegistryError("device registry must be {'version': 1, 'devices': [...]}")
    devices: dict[str, RegisteredDevice] = {}
    for entry in data["devices"]:
        if not isinstance(entry, dict):
            raise DeviceRegistryError("device entry must be an object")
        address = parse_ip(str(entry.get("wgAddress", "")))
        device_id = entry.get("deviceId")
        organization_id = entry.get("organizationId")
        revoked = entry.get("revoked", False)
        if address is None or not isinstance(device_id, str) or not device_id:
            raise DeviceRegistryError("device entry needs deviceId and a valid wgAddress")
        if not isinstance(organization_id, str) or not organization_id or not isinstance(revoked, bool):
            raise DeviceRegistryError(f"device {device_id!r}: organizationId and boolean revoked are required")
        key = str(address)
        if key in devices:
            # Jedna adresa = jeden peer; duplicita by byla nejednoznačná.
            raise DeviceRegistryError(f"wgAddress {key} is listed twice")
        devices[key] = RegisteredDevice(device_id, key, organization_id, revoked)
    return devices


class FileDeviceRegistry:
    """Načte registr znovu, jen když se změní mtime souboru."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._mtime: float | None = None
        self._devices: dict[str, RegisteredDevice] | None = None

    def devices(self) -> dict[str, RegisteredDevice] | None:
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            return None
        if self._devices is None or mtime != self._mtime:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    parsed = parse_registry(json.load(fh))
            except (OSError, ValueError) as exc:
                logger.error("SECURITY_EVENT: device_registry_unreadable", error=type(exc).__name__)
                return None
            self._devices, self._mtime = parsed, mtime
        return self._devices


_registries: dict[str, FileDeviceRegistry] = {}


def _registry(path: str) -> FileDeviceRegistry:
    registry = _registries.get(path)
    if registry is None:
        registry = _registries[path] = FileDeviceRegistry(path)
    return registry


def decide(devices: dict[str, RegisteredDevice] | None, client_ip: str | None, organization_id: str | None) -> BindingDecision:
    if devices is None:
        return "registry_unavailable"
    address = parse_ip(client_ip)
    device = devices.get(str(address)) if address is not None else None
    if device is None:
        return "unknown_device"
    if device.revoked:
        return "revoked_device"
    if not organization_id or device.organization_id != organization_id:
        return "organization_mismatch"
    return "allow"


def binding_applies() -> bool:
    from app.platform.config import get_settings
    from app.platform.http.exposure import ZONE_DESKTOP, ZONE_DEV

    settings = get_settings()
    return settings.device_binding_enforced and settings.effective_nc_zone in {ZONE_DESKTOP, ZONE_DEV}


def check_device_binding(client_ip: str | None, organization_id: str | None) -> BindingDecision:
    """``allow``, nebo důvod odmítnutí. Bez ``enforce`` vždy ``allow``."""
    if not binding_applies():
        return "allow"
    from app.platform.config import get_settings

    devices = _registry(get_settings().nc_device_registry_file.strip()).devices()
    decision = decide(devices, client_ip, organization_id)
    if decision != "allow":
        log = logger.error if decision == "registry_unavailable" else logger.warning
        log(
            "SECURITY_EVENT: device_binding_denied",
            reason=decision,
            client_ip=client_ip,
            organization_id=organization_id,
        )
    return decision
