"""Implements the behavior of the Land state."""

import asyncio
import logging
import dronekit
from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)
from state_machine.states.land import Land
from state_machine.states.charge import Charge
from flight.waypoint import goto
async def run(self: Land) -> None:
    """
    Implements the run method for the Land state.

    This method initiates the landing process of the drone and transitions to the Start state.

    Returns
    -------
    Start : State
        The next state after the drone has successfully landed.

    Notes
    -----
    This method is responsible for initiating the landing process of the drone and transitioning
    it back to the Start state, preparing for a new flight.

    """
    try:
        update_state("Land")
        update_drone(self.drone)
        
        logging.info("Land state running")

        # Instruct the drone to land
        self.drone.vehicle.airspeed = 20
        self.drone.vehicle.mode = dronekit.VehicleMode("GUIDED")
        await goto(self.drone, self.flight_settings.home_location.lat, self.flight_settings.home_location.lon, self.flight_settings.min_altitude_m)
        self.drone.vehicle.mode = dronekit.VehicleMode("LAND")
        for i in range(20):
            print("RUN ALEN's CODE HERE")
        logging.info("Land state complete.")
        return Charge(self.drone, self.flight_settings)
    except asyncio.CancelledError as ex:
        logging.error("Land state canceled")
        raise ex


# Setting the run_callable attribute of the Land class to the run function
Land.run_callable = run
