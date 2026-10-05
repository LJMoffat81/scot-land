# Georgist Wealth Engine - Resource Rent Module
# This module calculates the economic rent for sub-surface and marine resources.

import logging

logger = logging.getLogger(__name__)

class ResourceRentCalculator:
    """
    Calculates the estimated annual ground rent for natural resources.
    Formula: Area (ha) * Resource Intensity Factor
    """

    def __init__(self):
        # Default annual rent per hectare for different resource types
        # These are research-based estimates for the "Commons" rent
        self.intensity_factors = {
            "hydrocarbon_oil": 5000.0,    # High value per hectare
            "hydrocarbon_gas": 3000.0,     # Medium-high
            "offshore_wind": 1200.0,      # Medium
            "marine_aquaculture": 800.0,  # Medium-low
            "minerals_generic": 400.0,    # Low
        }

    def calculate(self, resource_type: str, area_ha: float) -> float:
        """
        Calculate rent based on the type of resource and the area it occupies.
        """
        factor = self.intensity_factors.get(resource_type, 100.0)
        rent = area_ha * factor
        return round(rent, 2)

# Singleton instance
calculator = ResourceRentCalculator()
