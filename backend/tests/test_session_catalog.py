from app.core.session_catalog import (
    CATALOG,
    MAX_OPTIONS,
    build_workout,
    dose_band,
    ranked_templates,
)

PACES = {'long_run_pace': 540, 'broken_threshold_pace': 410, 'tempo_pace': 420,
         'interval_pace': 375, 'interval_pace_fast': 365}


def pick(templates):
    seen, out = set(), []
    for t in templates:
        if t.family not in seen:
            seen.add(t.family); out.append(t)
    return out[:MAX_OPTIONS]


def test_catalog_keys_unique_and_every_template_builds():
    assert len({t.key for t in CATALOG}) == len(CATALOG)
    for t in CATALOG:
        w = build_workout(t, PACES)
        assert w['total_miles'] >= 3 and w['structure'] and 'Then Comfortably' not in w['structure']


def test_advanced_band_respects_floor_and_daniels_share():
    band = dose_band('threshold', 'advanced', 40, 410)
    assert band.low == 20 and 20 < band.high <= 40
    # Daniels: ~10% of weekly volume at T pace caps the top for modest mileage
    assert dose_band('threshold', 'advanced', 30, 410).high == 25


def test_low_volume_pulls_floor_down_for_comeback():
    assert dose_band('threshold', 'advanced', 12, 450).low < 20


def test_trail_goal_puts_hills_first_and_road_never_sees_hills():
    band = dose_band('intervals', 'advanced', 40, 375)
    trail = pick(ranked_templates('intervals', band, PACES, terrain='trail'))
    road = ranked_templates('intervals', band, PACES, terrain='road')
    assert trail[0].category == 'hills'
    assert not any(t.category == 'hills' for t in road)


def test_menu_mixes_time_and_distance_and_rotates_weekly():
    band = dose_band('threshold', 'advanced', 40, 410)
    weeks = [tuple(t.key for t in pick(ranked_templates('threshold', band, PACES, week_index=w))) for w in range(4)]
    assert all(len(set(k)) == 3 for k in weeks)
    assert len(set(weeks)) > 1
    first = pick(ranked_templates('threshold', band, PACES, week_index=0))
    assert any(not t.is_time_based for t in first)


def test_base_and_taper_keep_intervals_short():
    band = dose_band('intervals', 'advanced', 40, 375, phase='base')
    assert all(t.family in {'short_reps', 'time_reps', 'hills'}
               for t in ranked_templates('intervals', band, PACES, phase='base'))
    taper = dose_band('threshold', 'advanced', 40, 410, phase='taper')
    assert taper.high <= 15


def test_hills_are_effort_based_and_own_category():
    hill = next(t for t in CATALOG if t.category == 'hills')
    data = build_workout(hill, PACES)['prescription']
    assert data['category'] == 'hills' and all(s['pace_range_sec_per_mile'] is None for s in data['segments'])
