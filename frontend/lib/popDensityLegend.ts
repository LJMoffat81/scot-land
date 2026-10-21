/**
 * Shared people/km² range-legend props for the map key chip and Layers drawer
 * (FRONTEND-BATCH-4 SW-085 / SW-086). One helper so the two cannot drift.
 */

import {
  DEFAULT_VIEW_METRIC_ID,
  POP_DENSITY_LEGEND_SOURCE,
  metricById,
  rangeLegendTitle,
} from "@/lib/mapColourRamps";
import {
  rangeLegendFromStops,
  type RangeLegendStop,
} from "@/lib/mapLicenceCredits";

export type PopDensityLegendProps = {
  title: string;
  ranges: RangeLegendStop[];
  showNoData: true;
  mode: "bands";
  layerId: "density";
  source: typeof POP_DENSITY_LEGEND_SOURCE;
};

/** Props for `<MapRangeLegend />` on the default people/km² fill. */
export function popDensityLegendProps(): PopDensityLegendProps {
  const metric =
    metricById(DEFAULT_VIEW_METRIC_ID) ?? metricById("pop_density")!;
  const legend = rangeLegendFromStops(metric.stops, {
    metricId: metric.id,
    unit: metric.unit,
  });
  return {
    title: rangeLegendTitle(metric),
    ranges: legend.ranges,
    showNoData: true,
    mode: "bands",
    layerId: "density",
    source: POP_DENSITY_LEGEND_SOURCE,
  };
}
