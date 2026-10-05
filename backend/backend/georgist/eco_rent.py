# Georgist Wealth Engine - Ecological & Atmospheric Rent Module
# This module calculates rent for carbon sequestration and atmospheric resources.

import logging

logger = logging.getLogger(__name__)

class EcoAtmosphericRentCalculator:
    """
    Calculates the estimated annual ground rent for ecological and atmospheric assets.
    """

    def __init__(self):
        # Estimated value per hectare per year
        # Carbon rent is based on approximate carbon credit pricing
        self.rent_factors = {
            "peatland_sequestration": 150.0,  # Value of carbon storage
            "ancient_woodland": 200.0,      # Biodiversity & carbon value
            "solar_potential": 400.0,       # Atmospheric solar yield
            "wind_corridor": 600.0,         # Atmospheric wind yield
        }

    def calculate(self, resource_type: str, area_ha: float) -> float:
        """
        Calculate rent based on the ecological/atmospheric type and area.
        """
        factor = self.rent_factors.get(resource_type, 50.0)
        rent = area_ha * factor
        return round(rent, 2)

# Singleton instance
calculator = EcoAtmosphericRentCalculator()
