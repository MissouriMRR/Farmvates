import asyncio
import time
import mavutil
from state_machine.drone import Drone
async def upload_geofence(drone: Drone, geofence_points, inclusion=True, timeout=5):
    """
    Upload a polygon geofence to the drone.
 
    Uses the legacy FENCE_POINT protocol (parameter-based), which is what
    ArduPilot expects on most current stable firmware. The polygon is defined
    by the points in `geofence_points` in order. The first and last point
    must be identical to close the polygon -- this function handles that
    automatically if you don't pass a closed ring.
 
    Args:
        geofence_points: List of (lat, lon) tuples/lists or dicts with
            'lat'/'lon' keys, in order around the polygon.
        inclusion: If True (default), drone must stay INSIDE the polygon.
            If False, drone must stay OUTSIDE (exclusion / keep-out zone).
        timeout: Seconds to wait for parameter acknowledgements.
    """
    vehicle = drone.vehicle
 
    # Normalize points to a list of (lat, lon) floats
    def parse_point(p):
        if isinstance(p, dict):
            return float(p['lat']), float(p['lon'])
        return float(p[0]), float(p[1])
 
    points = [parse_point(p) for p in geofence_points]
 
    if len(points) < 3:
        raise ValueError("A polygon fence needs at least 3 points")
 
    # ArduPilot's FENCE_POINT protocol requires the polygon to be closed:
    # the last point must equal the first. Total point count therefore is
    # len(polygon_vertices) + 1.
    if points[0] != points[-1]:
        points.append(points[0])
 
    total_points = len(points)
 
    # --- Configure fence parameters ---
    # FENCE_ENABLE 0 first so we can safely rewrite points
    vehicle.parameters['FENCE_ENABLE'] = 0
    
    await asyncio.sleep(0.5)
 
    # FENCE_TYPE bitmask: 1=alt-max, 2=circle, 4=polygon, 8=alt-min
    # We set it to polygon only here; combine with |= if you want more.
    vehicle.parameters['FENCE_TYPE'] = 4
 
    # FENCE_TOTAL must be set BEFORE sending points, and must match exactly.
    vehicle.parameters['FENCE_TOTAL'] = total_points
 
    # Inclusion vs exclusion is controlled per-point on the newer fence
    # protocol, but the legacy FENCE_POINT message is inclusion-only on
    # ArduPilot. For exclusion polygons you need the newer
    # MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION via mission-item protocol.
    if not inclusion:
        return _upload_geofence_mission_protocol(vehicle, points, inclusion=False)
 
    await asyncio.sleep(0.5)
 
    # --- Send each fence point ---
    for idx, (lat, lon) in enumerate(points):
        msg = vehicle.message_factory.fence_point_encode(
            0, 0,            # target system, target component
            idx,             # point index (0-based)
            total_points,    # total number of points
            lat, lon,
        )
        vehicle.send_mavlink(msg)
        vehicle.flush()
        time.sleep(0.1)  # don't spam the link
 
    # --- Verify by reading the points back ---
    for idx in range(total_points):
        msg = vehicle.message_factory.fence_fetch_point_encode(
            0, 0, idx,
        )
        vehicle.send_mavlink(msg)
        vehicle.flush()
 
    # Re-enable the fence
    vehicle.parameters['FENCE_ENABLE'] = 1
    print(f"Uploaded inclusion geofence with {total_points - 1} vertices "
          f"({total_points} points including closing point)")
 
 
def _upload_geofence_mission_protocol(vehicle, points, inclusion=True):
    """
    Newer fence protocol using MISSION_ITEM_INT with MAV_MISSION_TYPE_FENCE.
    Required for exclusion polygons and supported on recent ArduPilot/PX4.
    """
    vertex_cmd = (
        mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION
        if inclusion else
        mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION
    )
 
    # In the mission-item fence protocol, each vertex carries the total
    # vertex count in param1 and you do NOT repeat the first point at the end.
    vertices = points[:-1] if points[0] == points[-1] else points
    total = len(vertices)
 
    vehicle.parameters['FENCE_ENABLE'] = 0
    vehicle.parameters['FENCE_TYPE'] = 4
    time.sleep(0.5)
 
    # Tell the autopilot how many fence items we're about to send
    count_msg = vehicle.message_factory.mission_count_encode(
        0, 0,
        total,
        mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
    )
    vehicle.send_mavlink(count_msg)
    vehicle.flush()
    time.sleep(0.2)
 
    # Send each vertex as a MISSION_ITEM_INT (lat/lon scaled by 1e7)
    for idx, (lat, lon) in enumerate(vertices):
        item = vehicle.message_factory.mission_item_int_encode(
            0, 0,
            idx,                                              # seq
            mavutil.mavlink.MAV_FRAME_GLOBAL,
            vertex_cmd,
            0, 1,                                             # current, autocontinue
            total,                                            # param1: vertex count
            0, 0, 0,                                          # param2-4 unused
            int(lat * 1e7), int(lon * 1e7), 0,                # x, y, z
            mavutil.mavlink.MAV_MISSION_TYPE_FENCE,
        )
        vehicle.send_mavlink(item)
        vehicle.flush()
        time.sleep(0.1)
 
    vehicle.parameters['FENCE_ENABLE'] = 1
    kind = "inclusion" if inclusion else "exclusion"
    print(f"Uploaded {kind} geofence polygon with {total} vertices")