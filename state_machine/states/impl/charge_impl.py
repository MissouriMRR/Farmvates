"""Implements the behavior of the Land state."""

import asyncio
import logging

from state_machine.state_tracker import (
    update_state,
    update_drone,
    
)
from state_machine.states.charge import Charge
from state_machine.states.start import Start

async def run(self: Charge) -> None:
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
        update_state("Charge")
        update_drone(self.drone)
        
        logging.info("Charge state running")
        while True:
            if self.drone.get_battery_percentage() >= 95:
                break
            logging.logger.info(f"Battery at {self.drone.get_battery_percentage()}%, waiting to charge...")
            await asyncio.sleep(30)

        logging.info("Charge state complete.")
        return Start(self.drone, self.flight_settings)
    except asyncio.CancelledError as ex:
        logging.error("Charge state canceled")
        raise ex


# Setting the run_callable attribute of the Charge class to the run function
Charge.run_callable = run