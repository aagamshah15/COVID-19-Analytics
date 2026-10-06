"""Seasonal forcing shared by training (M1, M2) and the scenario layer. NumPy only, so the cloud
API can run scenarios without the training stack."""

from __future__ import annotations

import numpy as np

# Seasonality is a temperate-zone effect: none inside the tropics, rising linearly to full
# strength at 40 degrees (an assumption; the amplitude itself is estimated). A first version
# ramped up from the equator, which gave India and Bangladesh a winter cycle they don't have.
SEASON_TROPIC_LATITUDE = 23.5
SEASON_FULL_LATITUDE = 40.0


def season_weight(latitude):
    """0 inside the tropics, rising linearly to 1 at 40 degrees north or south."""
    span = SEASON_FULL_LATITUDE - SEASON_TROPIC_LATITUDE
    return np.clip((np.abs(latitude) - SEASON_TROPIC_LATITUDE) / span, 0.0, 1.0)


def hemisphere_day(day_of_year, latitude):
    """Day of year shifted by half a year in the Southern Hemisphere, so both share one season."""
    return np.where(np.asarray(latitude) < 0, (np.asarray(day_of_year) + 182.5) % 365, day_of_year)
