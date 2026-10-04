export type ContextKind = "raster" | "fill" | "line" | "circle";

export type ContextLayer = {
  id: string;
  label: string;
  group: "Sea" | "Energy" | "Place" | "Use";
  kind: ContextKind;
  attribution: string;
  title: string;
  minzoom: number;
  maxzoom: number;
  color: string;
  opacity?: number;
};

const nsta =
  "Contains information provided by the North Sea Transition Authority and/or other third parties.";
const sg =
  "Contains information from the Scottish Government (Marine Scotland) licensed under the Open Government Licence v3.0.";
const ukho =
  "Contains information from the United Kingdom Hydrographic Office and the Scottish Government (Marine Scotland), licensed under the Open Government Licence v3.0.";
const ces =
  "Contains public sector information, licensed under the Open Government Licence v3.0, from Crown Estate Scotland.";

export const CONTEXT_LAYERS: ContextLayer[] = [
  {
    id: "sea-12nm",
    label: "12 mile sea",
    group: "Sea",
    kind: "raster",
    attribution: ukho,
    title: "Territorial sea, 12 nautical miles. " + ukho,
    minzoom: 3,
    maxzoom: 18,
    color: "#0b1e3a",
    opacity: 0.95,
  },
  {
    id: "marine-regions",
    label: "Marine regions",
    group: "Sea",
    kind: "raster",
    attribution:
      "Contains information from the Scottish Government licensed under the Open Government Licence v3.0.",
    title:
      "Scottish marine regions. Contains information from the Scottish Government licensed under the Open Government Licence v3.0.",
    minzoom: 3,
    maxzoom: 18,
    color: "#0b1e3a",
    opacity: 0.9,
  },
  {
    id: "scottish-zone",
    label: "Scottish zone",
    group: "Sea",
    kind: "raster",
    attribution: ukho,
    title: "Scottish zone out to 200 nautical miles. " + ukho,
    minzoom: 3,
    maxzoom: 18,
    color: "#0b1e3a",
    opacity: 0.95,
  },
  {
    id: "harbours",
    label: "Harbours",
    group: "Sea",
    kind: "raster",
    attribution: sg,
    title: "Statutory harbour limits. Indicative, not a legal boundary. " + sg,
    minzoom: 7,
    maxzoom: 18,
    color: "#0b1e3a",
    opacity: 0.9,
  },
  {
    id: "oil-fields",
    label: "Oil and gas fields",
    group: "Energy",
    kind: "fill",
    attribution: nsta,
    title: "Offshore fields. A resource rent, not a house-plot rate. " + nsta,
    minzoom: 0,
    maxzoom: 18,
    color: "#8a3b00",
  },
  {
    id: "platforms",
    label: "Platforms",
    group: "Energy",
    kind: "circle",
    attribution: nsta,
    title: "Surface platforms and floating installations. " + nsta,
    minzoom: 0,
    maxzoom: 18,
    color: "#8a3b00",
  },
  {
    id: "pipelines",
    label: "Pipelines",
    group: "Energy",
    kind: "line",
    attribution: nsta,
    title: "Offshore pipelines. " + nsta,
    minzoom: 0,
    maxzoom: 18,
    color: "#5c4a32",
  },
  {
    id: "wind-leases",
    label: "Wind leases",
    group: "Energy",
    kind: "fill",
    attribution: ces,
    title: "Signed offshore wind leases. Not a plan option. " + ces,
    minzoom: 0,
    maxzoom: 18,
    color: "#0076d3",
  },
  {
    id: "wind-plan",
    label: "Wind plan options",
    group: "Energy",
    kind: "raster",
    attribution: sg,
    title: "2020 offshore wind plan options. Not a signed lease. " + sg,
    minzoom: 4,
    maxzoom: 18,
    color: "#0076d3",
    opacity: 0.85,
  },
  {
    id: "wave-tidal",
    label: "Wave and tidal",
    group: "Energy",
    kind: "fill",
    attribution: ces,
    title: "Signed wave and tidal leases. " + ces,
    minzoom: 0,
    maxzoom: 18,
    color: "#0b6e62",
  },
  {
    id: "renewables",
    label: "Solar, wind, hydro",
    group: "Energy",
    kind: "circle",
    attribution:
      "Contains public sector information licensed under the Open Government Licence v3.0 from the Department for Energy Security and Net Zero.",
    title:
      "Operating or under construction, 150 kilowatts and above, Scotland only. Contains public sector information licensed under the Open Government Licence v3.0 from the Department for Energy Security and Net Zero.",
    minzoom: 0,
    maxzoom: 18,
    color: "#c47b00",
  },
  {
    id: "settlements",
    label: "Settlements",
    group: "Place",
    kind: "raster",
    attribution:
      "Contains National Records of Scotland data. Contains Ordnance Survey data © Crown copyright and database right.",
    title:
      "Census 2022 settlements, places of 500 people or more. Contains National Records of Scotland data. Contains Ordnance Survey data © Crown copyright and database right.",
    minzoom: 6,
    maxzoom: 18,
    color: "#0b1e3a",
    opacity: 0.65,
  },
  {
    id: "urban-rural",
    label: "Urban and rural",
    group: "Place",
    kind: "raster",
    attribution:
      "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right.",
    title:
      "Scottish Government urban and rural classes, including remote small towns. A location label, not a rent. Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right.",
    minzoom: 5,
    maxzoom: 9,
    color: "#0b1e3a",
    opacity: 0.45,
  },
  {
    id: "flood",
    label: "Flood extent",
    group: "Place",
    kind: "raster",
    attribution:
      "© SEPA. Licensed under the Open Government Licence v3.0.",
    title:
      "Medium-likelihood river and coastal flood extent. Later this can only reduce a rent. © SEPA. Licensed under the Open Government Licence v3.0.",
    minzoom: 8,
    maxzoom: 18,
    color: "#1d4e89",
    opacity: 0.55,
  },
  {
    id: "woodland",
    label: "Woodland",
    group: "Use",
    kind: "raster",
    attribution:
      "© Forestry Commission copyright. Contains Ordnance Survey data © Crown copyright and database right 2025. Licensed under the Open Government Licence v3.0.",
    title:
      "National Forest Inventory woodland, at least 0.5 hectare. A use, not a rent. © Forestry Commission copyright. Contains Ordnance Survey data © Crown copyright and database right 2025. Licensed under the Open Government Licence v3.0.",
    minzoom: 7,
    maxzoom: 18,
    color: "#1f6b3a",
    opacity: 0.85,
  },
];

export const CONTEXT_GROUPS = ["Sea", "Energy", "Place", "Use"] as const;
