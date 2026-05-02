"""Implements the behavior of the Start state."""

import asyncio
import logging

from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)
from state_machine.states.start import Start
from state_machine.states.state import State
from state_machine.states.takeoff import Takeoff


async def run(self: Start) -> State:
    """
    Implements the run method for the Start state.

    This method establishes a connection with the drone, waits for the drone to be
    discovered, ensures the drone has a global position estimate, arms the drone,
    and transitions to the Takeoff state.

    Returns
    -------
    Takeoff : State
        The next state after the Start state has successfully run.

    Notes
    -----
    This method is responsible for initializing the drone and transitioning it to the
    Takeoff state, which is the next step in the state machine.

    """
    try:
        update_state("Start")
        update_drone(self.drone)
        
        logging.info("Start state running")

        await self.drone.connect_drone()
        self.drone._vehicle.clear_mission()  # Clear any existing mission to prevent unintended takeoff
        while not self.drone._vehicle.armed:
            await asyncio.sleep(0.5)
            logging.info("Waiting for drone to be armed...")
        await self.drone.setGroundStationLocation()
        

        logging.info("Start state complete")
        return Takeoff(self.drone, self.flight_settings)
    except asyncio.CancelledError as ex:
        logging.error("Start state canceled")
        raise ex
    finally:
        pass


# Setting the run_callable attribute of the Start class to the run function
Start.run_callable = run
