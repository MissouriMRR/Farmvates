"""Implements the behavior of the Land state."""

import asyncio
import logging

from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)
from state_machine.states.emergencyLand import EmergencyLand


async def run(self: EmergencyLand) -> None:
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
        await self.drone.return_to_launch()

        logging.info("Land state complete.")
        return
    except asyncio.CancelledError as ex:
        logging.error("Land state canceled")
        raise ex


# Setting the run_callable attribute of the EmergencyLand class to the run function
EmergencyLand.run_callable = run