/**
 * Layer order helpers for basemap + Scot-LAND overlays (O2 / SHOWTHRU).
 */

type LayerLike = { id: string; type?: string };

type StyleLike = {
  getStyle?: () => { layers?: LayerLike[] } | undefined;
};

/** Id of the first symbol layer in the current style, if any. */
export function firstSymbolLayerId(
  map: StyleLike,
): string | undefined {
  const layers = map.getStyle?.()?.layers ?? [];
  for (const layer of layers) {
    if (layer.type === "symbol") return layer.id;
  }
  return undefined;
}

/** Id of the last raster layer in the current style, if any. */
export function lastRasterLayerId(map: StyleLike): string | undefined {
  const layers = map.getStyle?.()?.layers ?? [];
  let last: string | undefined;
  for (const layer of layers) {
    if (layer.type === "raster") last = layer.id;
  }
  return last;
}
