"""Class to contain setters, getters & parameters for current flight"""

from asyncio import Event
from enum import Enum
import logging
import sys
from typing import Final

from state_machine import mission_config
from state_machine.mission_config import MissionConfig, SimModeConfig

from dronekit import LocationGlobalRelative, LocationGlobal
DEFAULT_RUN_TITLE: Final[str] = "Test Flight"
DEFAULT_RUN_DESCRIPTION: Final[str] = "A test flight"
DEFAULT_STANDARD_OBJECT_COUNT: Final[int] = 5


class SimMode(Enum):
    """
    Distinguishes whether a drone is real, running in the sim, or running in airsim.
    """

    REAL = "real"
    SIM = "sim"
    AIRSIM = "airsim"


# pylint: disable=too-many-instance-attributes
class FlightSettings:
    """
    Class to contain basic information for a flight, as well as some flight parameters

    Attributes
    ----------
    _read_sim_mode: bool
        Whether the sim mode has been read. Used to determine when to show the message
        about the sim mode.
    __simple_takeoff: bool
        Sets if the drone will ascend vertically or at an angle
    __run_title: str
        The name for the current flight operation
    __run_description: str
        A small description for the current flight
    __mean_wind_speed: float
        The mean wind speed, in meters per second.
    __mean_wind_direction: float
        The mean wind direction, in degrees.
    __skip_waypoint: bool
        Whether to skip the waypoint state.
    __skip_odlc_and_airdrop: bool
        Whether to skip the ODLC and airdrop states.
    __standard_object_count: int
        The number of standard objects to attempt to find.
    __sim_mode: SimMode
        Whether the drone is real, running in the ardupilot sim, or running in airsim
    __mission_data_path: str
        The path to the JSON file containing the boundary and waypoint data.
    __yolo_status: Event
        An asyncio Event tracking whether the YOLO model has
        finished processing images.

    Methods
    -------
    from_mission_config() -> FlightSettings
        Creates a new FlightSettings object from the mission config
    simple_takeoff() -> bool
        Returns the status of the takeoff type for the flight
    simple_takeoff(simple_takeoff: bool) -> None
        Sets the parameter for a simple or diagonal takeoff
    skip_waypoint() -> bool
        Returns whether to skip the waypoint state.
    skip_odlc_and_airdrop() -> bool
        Returns whether to skip the ODLC and airdrop states.
    skip_waypoint(flag: bool) -> None
        Setter for configuring whether to skip the waypoint state.
    standard_object_count() -> int
        Returns the number of standard objects to attempt to find.
    standard_object_count(count: int) -> None
        Setter for the number of standard objects to attempt to find.
    mean_wind_speed() -> float
        Returns the mean wind speed, in meters per second.
    mean_wind_direction() -> float
        Returns the mean wind speed, in degrees.
    run_title() -> str
        `Returns the flight title
    run_title(new_title: str) -> None
        Sets a new title for the current flight
    run_description() -> str
        Returns the small description for the current flight
    run_description(new_description: str) -> None
        Sets a new description for the new flight
    sim_mode() -> SimMode
        Returns the simulation mode
    sim_mode(sim_mode: SimMode) -> None
        Sets the simulation mode
    mission_data_path() -> str
        Return the path to the JSON file containing the boundary and waypoint data.
    mission_data_path(mission_data_path: str) -> None
        Set the path to the JSON file containing the boundary and waypoint data.
    """

    _read_sim_mode: bool = False


    # pylint: disable=too-many-arguments
    def __init__(
        self,
        exported_at: str,
        waypoints: list,
        loops: int,
        ground_station_lat: float,
        ground_station_lon: float,
        ground_station_address: str,
        cruise_speed_ms: float,
        min_altitude_m: float,
        begin_landing_pct: float,
        emergency_land_pct: float,
        log_battery_events: bool,
        log_flight_hours: bool,
        low_battery_alert: bool,
        geofence_enabled: bool,
        geofence_points: list,
        loop_until_low_battery: bool,
        sim_mode: SimMode = SimMode.REAL,
    ) -> None:
        self.__exported_at: str = exported_at
        self.__loops: int = loops
        self.__ground_station_lat: float = ground_station_lat
        self.__ground_station_lon: float = ground_station_lon
        self.__ground_station_address: str = ground_station_address
        self.__cruise_speed_ms: float = cruise_speed_ms
        self.__min_altitude_m: float = min_altitude_m
        self.__begin_landing_pct: float = begin_landing_pct
        self.__emergency_land_pct: float = emergency_land_pct
        self.__log_battery_events: bool = log_battery_events
        self.__log_flight_hours: bool = log_flight_hours
        self.__low_battery_alert: bool = low_battery_alert
        self.__geofence_enabled: bool = geofence_enabled
        self.__loop_until_low_battery: bool = loop_until_low_battery
        self.__sim_mode: SimMode = sim_mode
        self.__yolo_status: Event = Event()
        

        # Parse waypoints → LocationGlobalRelative (altitude from min_altitude_m)
        self.__waypoints: list[LocationGlobalRelative] = [
            LocationGlobalRelative(wp["lat"], wp["lon"], min_altitude_m)
            for wp in sorted(waypoints, key=lambda w: w["index"])
        ]

        # Parse geofence → LocationGlobal (no altitude for boundary points)
        self.__geofence_points: list[LocationGlobal] = [
            LocationGlobal(pt["lat"], pt["lon"], 0.0)
            for pt in sorted(geofence_points, key=lambda p: p["index"])
        ] if geofence_enabled else []

    @staticmethod
    def from_mission_config() -> "FlightSettings":
        """
        Creates a new FlightSettings object from the mission config file and command line
        arguments

        Returns
        -------
        FlightSettings
            A FlightSettings object with settings from mission_config.json.
        """
        sim_flag: bool = "-s" in sys.argv or "--sim" in sys.argv
        airsim_flag: bool = "-a" in sys.argv or "--airsim" in sys.argv
        sim_mode: SimMode = (
            SimMode.AIRSIM if airsim_flag else SimMode.SIM if sim_flag else SimMode.REAL
        )
        if not FlightSettings._read_sim_mode:
            FlightSettings._read_sim_mode = True
            logging.info(
                "Running in %s mode."
                " Pass -s or --sim to run in sim mode."
                " Pass -a or --airsim to run in airsim mode.",
                sim_mode.name,
            )

        config: MissionConfig = mission_config.get_mission_config()
        
        config_settings: FlightSettings = FlightSettings(
            config["mission"]["exported_at"],

            config["mission"]["flight_path"]["waypoints"],
            config["mission"]["flight_path"]["loops"],

            config["mission"]["ground_station"]["lat"],
            config["mission"]["ground_station"]["lon"],
            config["mission"]["ground_station"]["address"],

            config["mission"]["advanced"]["cruise_speed_ms"],
            config["mission"]["advanced"]["min_altitude_m"],
            config["mission"]["advanced"]["begin_landing_pct"],
            config["mission"]["advanced"]["emergency_land_pct"],
            config["mission"]["advanced"]["log_battery_events"],
            config["mission"]["advanced"]["log_flight_hours"],
            config["mission"]["advanced"]["low_battery_alert"],

            config["mission"]["geofence"]["enabled"],
            config["mission"]["geofence"]["points"],
            config["mission"]["advanced"]["loop_until_low_battery"],

            sim_mode,
        )
        return config_settings

    @property
    def loop_until_low_battery(self) -> bool:
        """
        Returns whether to loop through the waypoints until the battery is low.

        Returns
        -------
        bool
            Whether to loop through the waypoints until the battery is low.
        """
        return self.__loop_until_low_battery
    @property
    def exported_at(self) -> str:
        return self.__exported_at

    @property
    def waypoints(self) -> list:
        return self.__waypoints

    @property
    def loops(self) -> int:
        return self.__loops

    @property
    def ground_station_lat(self) -> float:
        return self.__ground_station_lat

    @property
    def ground_station_lon(self) -> float:
        return self.__ground_station_lon

    @property
    def ground_station_address(self) -> str:
        return self.__ground_station_address

    @property
    def cruise_speed_ms(self) -> float:
        return self.__cruise_speed_ms

    @property
    def min_altitude_m(self) -> float:
        return self.__min_altitude_m

    @property
    def begin_landing_pct(self) -> float:
        return self.__begin_landing_pct

    @property
    def emergency_land_pct(self) -> float:
        return self.__emergency_land_pct

    @property
    def log_battery_events(self) -> bool:
        return self.__log_battery_events

    @property
    def log_flight_hours(self) -> bool:
        return self.__log_flight_hours

    @property
    def low_battery_alert(self) -> bool:
        return self.__low_battery_alert

    @property
    def geofence_enabled(self) -> bool:
        return self.__geofence_enabled

    @property
    def geofence_points(self) -> list:
        return self.__geofence_points

    @property
    def sim_mode(self) -> SimMode:
        return self.__sim_mode

    @property
    def yolo_status(self) -> Event:
        return self.__yolo_status