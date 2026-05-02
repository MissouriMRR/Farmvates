"""Implement the behavior of the Waypoint state."""

# pylint: disable=too-many-locals

import asyncio
import logging
import traceback
from typing import Final

import dronekit

import utm

from flight.extract_gps import extract_gps, GPSData
from flight.extract_gps import (
    WaypointUtm as WaylistUtm,
    BoundaryPointUtm as BoundarylistUtm,
)

from flight.waypoint.geometry import LineSegment, Point
from flight.waypoint.goto import move_to
from flight.waypoint.graph import GraphNode
from flight.waypoint import pathfinding
from flight.waypoint.geofence import upload_geofence

from state_machine.states.state import State
from state_machine.states.start import Start
from state_machine.states.waypoint import Waypoint
from state_machine.states.land import Land
from state_machine.states.emergencyLand import EmergencyLand
from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)

BOUNDARY_SHRINKAGE: Final[float] = 5.0  # in meters
WAYPOINT_AIR_SPEED: Final[float] = 25.0  # in meters/second


async def run(self: Waypoint) -> State:
    """
    Run method implementation for the Waypoint state.

    This method instructs the drone to navigate to a specified waypoint and
    transitions to the Airdrop or ODLC State.

    Returns
    -------
    Airdrop : State
        The next state after successfully reaching the specified waypoint and
        initiating the Airdrop process.
    ODLC : State
        The next state after successfully reaching the specified waypoint and
        initiating the ODLC process.

    Notes
    -----
    This method is responsible for guiding the drone to a predefined waypoint in its flight path.
    Upon reaching the waypoint, it transitions the drone to the Land state to initiate landing.

    """

    try:
        update_state("Waypoint")
        update_drone(self.drone)

        logging.info("Waypoint state running")  
        total = len(self.drone._vehicle.commands)
        
        dots=""
        while self.drone._vehicle.commands.next < total or self.flight_settings.loop_until_low_battery:
            print(self.drone._vehicle.commands.next)
            await asyncio.sleep(5)
            logging.info("Waypoint state still running"+dots)  
            if(self.drone._vehicle.battery.level < self.flight_settings.emergency_land_pct and not self.flight_settings.loop_until_low_battery):
                logging.info("Emergency battery threshold reached, landing immediately")
                return EmergencyLand(self.drone, self.flight_settings)
            elif(self.drone._vehicle.battery.level < self.flight_settings.begin_landing_pct and self.flight_settings.loop_until_low_battery):
                logging.info("Low battery threshold reached, ending mission")
                return Land(self.drone, self.flight_settings)
            if(self.drone._vehicle.mode.name != "AUTO"):

                return Start(self.drone, self.flight_settings)
            dots+="."
            if(len(dots)>3):
                dots=""

        upload_geofence(self.drone, self.flight_settings.geofence_points, inclusion=True)
        logging.info("Loops complete, landing")
        return Land(self.drone, self.flight_settings)
            
        # mission done
        

    except asyncio.CancelledError as ex:
        logging.error("Waypoint state canceled")
        raise ex
    except Exception as ex:
        logging.error(f"Error in Waypoint state: {ex}")
        traceback.print_exc()
        raise ex
    finally:
        pass

# Set the run_callable attribute of the Waypoint class to the run function
Waypoint.run_callable = run
