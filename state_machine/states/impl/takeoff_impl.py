"""Implements the behavior of the Takeoff state."""

import asyncio
import logging
import time
from flight.extract_gps import extract_gps
from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)
from state_machine.states.state import State
from state_machine.states.takeoff import Takeoff
from state_machine.states.land import Land
from state_machine.states.waypoint import Waypoint
from state_machine.states.start import Start
import dronekit


async def run(self: Takeoff) -> State:
    """
    Implements the run method for the Takeoff state.

    This method initiates the drone takeoff process and transitions to the Waypoint state.

    Returns
    -------
    Waypoint : State
        The next state after a successful takeoff.

    Raises
    ------
    asyncio.CancelledError
        If the execution of the Takeoff state is canceled.

    Notes
    -----
    This method is responsible for taking off the drone and transitioning it to the
    Waypoint state, which represents the navigation phase to reach a specified waypoint.

    """
    try:
        update_state("Takeoff")
        update_drone(self.drone)

        logging.info("Takeoff state running")

   

        cmds = self.drone._vehicle.commands
        #cmd1=Command( 0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 0, 10)
        cmds.add(dronekit.Command( 0, 0, 0, dronekit.mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, dronekit.mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 0, 10))
        cmds.add(dronekit.Command( 0, 0, 0, dronekit.mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, dronekit.mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 0, 10))
        if(self.flight_settings.loops == 0 and self.flight_settings.loop_until_low_battery):
            self.flight_settings.loops=1
        for i in range(self.flight_settings.loops):
            #cmds.add(dronekit.Command(0, 0, 0, dronekit.mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, dronekit.mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0,0,0, self.flight_settings.min_altitude_m))
            for waypoint in self.flight_settings.waypoints:
                cmds.add(
                    dronekit.Command(0,0,0, dronekit.mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, dronekit.mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0, 0, 0, 0, 0, 0,
                    waypoint.lat, waypoint.lon, waypoint.alt)
                )
                print(f"Added waypoint: {waypoint.lat}, {waypoint.lon}, {waypoint.alt}")
        
        
        cmds.add(
            dronekit.Command(0,0,0, dronekit.mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, dronekit.mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 0, 0, 0, 0, 0,
            self.flight_settings.waypoints[0].lat, self.flight_settings.waypoints[0].lon, self.flight_settings.waypoints[0].alt)
        )
        

        cmds.upload()
        if self.drone._vehicle.armed:
            logging.info("Drone is armed, setting to guided mode")
            self.drone._vehicle.mode = dronekit.VehicleMode("GUIDED")
            while self.drone._vehicle.mode.name != "GUIDED":
                logging.info("Waiting for drone to enter guided mode...")
                await asyncio.sleep(0.5)
        else:
            return Start(self.drone, self.flight_settings)
        

        while(self.drone._vehicle.mode.name != "AUTO"):
            await asyncio.sleep(0.5)
            logging.info("Waiting for mission to start...")
            
        return Waypoint(self.drone, self.flight_settings)


        
    except asyncio.CancelledError as ex:
        logging.error("Takeoff state canceled")
        raise ex
    finally:
        pass


# Setting the run_callable attribute of the Takeoff class to the run function
Takeoff.run_callable = run
