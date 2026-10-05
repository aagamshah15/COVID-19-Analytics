// Writes data/reference/country_centroids.csv: the spherical centroid of every country in the
// world-atlas 1:50m map, keyed by ISO 3166 numeric code. The simulator uses latitude to scale
// seasonality (strong at high latitudes, weak in the tropics) and to choose its phase by hemisphere.
// Country centroids don't change, so the output is committed; rerun with:
//   node scripts/country_centroids.mjs   (needs `npm ci` in dashboard/)
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(new URL("../dashboard/package.json", import.meta.url));
const { geoArea, geoCentroid } = require("d3-geo");
const { feature } = require("topojson-client");
const atlas = JSON.parse(readFileSync(require.resolve("world-atlas/countries-50m.json"), "utf8"));

// A few codes have more than one shape (Australia and the Ashmore and Cartier Islands share 036):
// keep the largest.
const largest = new Map();
for (const f of feature(atlas, atlas.objects.countries).features) {
  if (f.id === undefined) continue;
  const current = largest.get(f.id);
  if (!current || geoArea(f) > geoArea(current)) largest.set(f.id, f);
}
const rows = [...largest.values()]
  .map((f) => {
    const [lon, lat] = geoCentroid(f);
    return `${f.id},${JSON.stringify(f.properties.name)},${lat.toFixed(3)},${lon.toFixed(3)}`;
  })
  .sort();
writeFileSync(new URL("../data/reference/country_centroids.csv", import.meta.url), ["iso_numeric,name,latitude,longitude", ...rows].join("\n") + "\n");
console.log(`${rows.length} centroids written`);
