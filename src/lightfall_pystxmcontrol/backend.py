"""Lightfall DeviceBackend for simulated pystxmcontrol devices.

This backend builds and connects PystxmAxis and PystxmCounter devices
in simulation mode and registers them as DeviceInfo entries in the
Lightfall device catalog.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from loguru import logger

from lightfall.devices.base import DeviceBackend
from lightfall.devices.model import (
    ConnectionType,
    DeviceCategory,
    DeviceConfiguration,
    DeviceInfo,
    DeviceState,
    DeviceStatus,
    MaintenanceRecord,
)

from . import config
from .devices import PystxmAxis, PystxmCounter


class PystxmStxmBackend(DeviceBackend):
    """Lightfall backend exposing simulated pystxmcontrol devices.

    Builds and connects PystxmAxis (SampleX, SampleY) and PystxmCounter
    (Counter1) in simulation mode and registers them with DeviceInfo
    entries in the Lightfall device catalog.

    Example:
        >>> backend = PystxmStxmBackend()
        >>> backend.connect()
        >>> devices = backend.list_devices()
        >>> motor = backend.get_device_by_name("SampleX")
        >>> motor._ophyd_device.name
        'SampleX'
    """

    def __init__(self) -> None:
        """Initialize the pystxmcontrol backend."""
        self._devices: dict[UUID, DeviceInfo] = {}
        self._configurations: dict[UUID, list[DeviceConfiguration]] = {}
        self._maintenance: dict[UUID, list[MaintenanceRecord]] = {}
        self._connected = False
        self._ophyd_devices: dict[str, Any] = {}

    # === Identity ===

    @property
    def name(self) -> str:
        """Get the backend name."""
        return "pystxmcontrol"

    @property
    def is_connected(self) -> bool:
        """Check if backend is connected."""
        return self._connected

    # === Lifecycle ===

    def connect(self) -> bool:
        """Connect and initialize simulated pystxmcontrol devices.

        Builds PystxmAxis (SampleX, SampleY) and PystxmCounter (Counter1),
        connects them via asyncio.run, and registers DeviceInfo entries.

        Note: asyncio.run is a temporary scaffold. Task 8 will route the
        async connect through Lightfall's BlueskyEngine background loop
        instead. The only side-effect callers observe is the populated
        self._devices dict, so this approach is transparent to the rest
        of Lightfall for now.

        Returns:
            True if connection was successful.
        """
        if self._connected:
            return True

        try:
            specs = []
            for axis_name, axis_cfg in config.DEFAULT_AXES.items():
                dev = PystxmAxis(axis_cfg, name=axis_name)
                specs.append((axis_name, dev, DeviceCategory.MOTOR))

            counter = PystxmCounter(config.DEFAULT_COUNTER, dwell=1.0, name="Counter1")
            specs.append(("Counter1", counter, DeviceCategory.DETECTOR))

            async def _connect_all():
                for _, dev, _ in specs:
                    await dev.connect(mock=False)

            # Temporary scaffold: drive the ophyd-async connect outside any
            # running event loop.  Task 8 will replace this with the engine loop.
            asyncio.run(_connect_all())

            for dev_name, dev, category in specs:
                info = DeviceInfo(
                    name=dev_name,
                    description=f"Simulated pystxmcontrol {category.value}",
                    device_class=f"lightfall_pystxmcontrol.devices:{type(dev).__name__}",
                    category=category,
                    connection_type=ConnectionType.SIMULATED,
                    prefix=dev_name,
                    tags=[category.value.lower(), "pystxmcontrol", "simulated"],
                    metadata={},
                )
                info._ophyd_device = dev
                self._add_device_internal(info)
                self._ophyd_devices[dev_name] = dev

            self._connected = True
            logger.info("PystxmStxmBackend connected with {} devices", len(self._devices))
            return True

        except Exception as e:
            logger.error("Failed to connect PystxmStxmBackend: {}", e)
            return False

    def disconnect(self) -> None:
        """Disconnect and clear all device state."""
        self._connected = False
        self._ophyd_devices.clear()
        self._devices.clear()
        self._configurations.clear()
        self._maintenance.clear()
        logger.info("PystxmStxmBackend disconnected")

    # === Internal helpers ===

    def _add_device_internal(self, device: DeviceInfo) -> None:
        """Internal method to add device to storage (mirrors MockBackend)."""
        self._devices[device.id] = device
        self._configurations[device.id] = []
        self._maintenance[device.id] = []

        # Create default configuration
        default_config = DeviceConfiguration(
            name="default",
            device_id=device.id,
            parameters=device.metadata.copy(),
        )
        self._configurations[device.id].append(default_config)

        # Set device state
        device._state = DeviceState(
            device_id=device.id,
            status=DeviceStatus.ONLINE if device._ophyd_device else DeviceStatus.OFFLINE,
            connected=device._ophyd_device is not None,
        )

    # === Device CRUD Operations ===

    def get_device(self, device_id: UUID) -> DeviceInfo | None:
        """Get a device by ID."""
        return self._devices.get(device_id)

    def get_device_by_name(self, name: str) -> DeviceInfo | None:
        """Get a device by name."""
        for device in self._devices.values():
            if device.name == name:
                return device
        return None

    def get_device_by_prefix(self, prefix: str) -> DeviceInfo | None:
        """Get a device by connection prefix."""
        for device in self._devices.values():
            if device.prefix == prefix:
                return device
        return None

    def list_devices(
        self,
        category: DeviceCategory | None = None,
        beamline: str | None = None,
        active_only: bool = True,
    ) -> list[DeviceInfo]:
        """List devices with optional filtering."""
        result = []
        for device in self._devices.values():
            if active_only and not device.active:
                continue
            if category and device.category != category:
                continue
            if beamline and device.beamline != beamline:
                continue
            result.append(device)
        return result

    def search_devices(self, query: str) -> list[DeviceInfo]:
        """Search devices by query string."""
        return [d for d in self._devices.values() if d.matches_search(query)]

    def add_device(self, device: DeviceInfo) -> bool:
        """Add a new device."""
        if device.id in self._devices:
            return False
        self._add_device_internal(device)
        return True

    def update_device(self, device: DeviceInfo) -> bool:
        """Update an existing device."""
        if device.id not in self._devices:
            return False
        device.modified = datetime.now()
        self._devices[device.id] = device
        return True

    def remove_device(self, device_id: UUID) -> bool:
        """Remove a device."""
        if device_id not in self._devices:
            return False
        del self._devices[device_id]
        self._configurations.pop(device_id, None)
        self._maintenance.pop(device_id, None)
        return True

    # === Configuration Operations ===

    def get_device_configurations(
        self, device_id: UUID
    ) -> list[DeviceConfiguration]:
        """Get all configurations for a device."""
        return self._configurations.get(device_id, [])

    def get_configuration(
        self, device_id: UUID, config_name: str
    ) -> DeviceConfiguration | None:
        """Get a specific configuration by name."""
        configs = self._configurations.get(device_id, [])
        for cfg in configs:
            if cfg.name == config_name:
                return cfg
        return None

    def save_configuration(self, cfg: DeviceConfiguration) -> bool:
        """Save a device configuration."""
        if cfg.device_id is None:
            return False
        if cfg.device_id not in self._configurations:
            self._configurations[cfg.device_id] = []

        configs = self._configurations[cfg.device_id]
        for i, existing in enumerate(configs):
            if existing.name == cfg.name:
                configs[i] = cfg
                return True

        configs.append(cfg)
        return True

    def delete_configuration(self, config_id: UUID) -> bool:
        """Delete a configuration."""
        for _device_id, configs in self._configurations.items():
            for i, cfg in enumerate(configs):
                if cfg.id == config_id:
                    del configs[i]
                    return True
        return False

    # === Maintenance Records ===

    def get_maintenance_history(
        self, device_id: UUID, limit: int = 100
    ) -> list[MaintenanceRecord]:
        """Get maintenance history for a device."""
        records = self._maintenance.get(device_id, [])
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[:limit]

    def add_maintenance_record(self, record: MaintenanceRecord) -> bool:
        """Add a maintenance record."""
        if record.device_id not in self._maintenance:
            self._maintenance[record.device_id] = []
        self._maintenance[record.device_id].append(record)
        return True

    # === Ophyd Device Access ===

    def get_ophyd_device(self, name: str) -> Any:
        """Get the ophyd-async device instance by name."""
        return self._ophyd_devices.get(name)

    def get_all_ophyd_devices(self) -> dict[str, Any]:
        """Get all ophyd-async device instances."""
        return dict(self._ophyd_devices)

    # === Introspection ===

    def get_backend_info(self) -> dict[str, Any]:
        """Get information about this backend."""
        return {
            "name": self.name,
            "connected": self.is_connected,
            "device_count": len(self._devices),
            "ophyd_device_count": len(self._ophyd_devices),
            "categories": list({d.category.value for d in self._devices.values()}),
        }
