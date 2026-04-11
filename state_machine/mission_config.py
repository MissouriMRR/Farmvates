"""Gets the mission configuration."""

import json
from typing import TextIO, TypedDict

import os
import sys
import time
import shutil
import platform
import glob
import os
import sys
import time
import json
import platform
import glob
import logging

# ── Configuration ────────────────────────────────────────────────────────────
POLL_INTERVAL = 2   # seconds between device checks
# ─────────────────────────────────────────────────────────────────────────────


def get_mount_points() -> list[str]:
    """Return a list of mount points for removable/external devices."""
    system = platform.system()

    if system == "Windows":
        import ctypes
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drive = f"{letter}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                # 2 = DRIVE_REMOVABLE, 5 = DRIVE_CDROM
                if drive_type in (2, 5):
                    drives.append(drive)
            bitmask >>= 1
        return drives

    elif system == "Darwin":  # macOS
        volumes = glob.glob("/Volumes/*")
        # Exclude the root macOS volume
        return [v for v in volumes if v != "/Volumes/Macintosh HD"]

    else:  # Linux
        # Check /media and /run/media for auto-mounted removable devices
        mount_points = []
        for base in ["/media", "/run/media"]:
            if os.path.isdir(base):
                # /run/media/<username>/<device>
                for entry in glob.glob(os.path.join(base, "*", "*")):
                    mount_points.append(entry)
                # /media/<device>  (older distros)
                for entry in glob.glob(os.path.join(base, "*")):
                    if os.path.isdir(entry) and entry not in mount_points:
                        mount_points.append(entry)
        return mount_points


def find_latest_json(mount_point: str) -> str | None:
    """Walk a mount point and return the path of the most recently modified JSON file."""
    json_files = glob.glob(os.path.join(mount_point, "**", "*.json"), recursive=True)
    if not json_files:
        return None
    return max(json_files, key=os.path.getmtime)






    



class SimModeConfig(TypedDict):
    """
    A configuration containing settings specific to each sim mode.

    Attributes
    ----------
    mission_data_path : str
        The path to the JSON file containing the boundary and waypoint data.
    """

    mission_data_path: str
    # CUSTOMIZE THIS: add attributes here


class WindConfig(TypedDict):
    """
    A configuration containing manually entered wind speed and direction.

    Attributes
    ----------
    mean_wind_speed : float
        The mean wind speed, in meters per second.
    mean_wind_direction : float
        The mean wind direction, in degrees.
        A value of 0 represents north, and 90 represents west.
    """

    mean_wind_speed: float
    mean_wind_direction: float


class MissionConfig(TypedDict):
    """
    A configuration for a flight mission.

    Attributes
    ----------
    run_title : str
        The name for the current flight operation.
    run_description : str
        A small description for the current flight.
    real_mode_config : SimModeConfig
        Settings to use when running in real mode.
    sim_mode_config : SimModeConfig
        Settings to use when running in real mode.
    airsim_mode_config : SimModeConfig
        Settings to use when running in real mode.
    wind : WindConfig
        Manually entered information on the wind.
    """

    run_title: str
    run_description: str
    real_mode_config: SimModeConfig
    sim_mode_config: SimModeConfig
    airsim_mode_config: SimModeConfig
    wind: WindConfig
    # CUSTOMIZE THIS: add attributes here


def get_mission_config() -> MissionConfig:
    """
    Get the mission configuration from mission_config.json

    Returns
    -------
    MissionConfig
        The mission configuration.
    """
    config_file: TextIO

    
    seen_devices: set[str] = set()

    try:
        logging.info("Looking for mission_config.json on removable devices...")
        while True:
            mounts = get_mount_points()

            if not mounts:
                logging.info(f"  No removable device detected, polling every {POLL_INTERVAL} seconds.")
            else:
                for mount in mounts:
                    if mount not in seen_devices:
                        logging.info(f"[+] Device detected: {mount}")
                        seen_devices.add(mount)

                    latest = find_latest_json(mount)
                    if latest:
                        with open(latest, "r", encoding="utf-8") as config_file:
                            return json.load(config_file)
                        logging.info(f"    Loaded data      : {data}")
                        
                    else:
                        logging.info(f"    No JSON files found on {mount}.")

                # Clean up stale entries (device removed between polls)
                seen_devices &= set(mounts)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    

