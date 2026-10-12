from spatial.grid import snap_to_w3w_grid


def test_snap_to_w3w_grid_is_stable():
    a = snap_to_w3w_grid(55.8642, -4.2518)
    b = snap_to_w3w_grid(55.8642, -4.2518)
    assert a.lat == b.lat and a.lng == b.lng
    assert a.area_sqm == 9.0
