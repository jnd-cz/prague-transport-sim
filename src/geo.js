// Game metres to WGS84 in the browser (#129): the city frame (data.frame: S-JTSK EPSG:5514 minus its
// origin) through the inverse Křovák projection (EPSG guidance note 7-2) on the Bessel ellipsoid, then
// a 7-parameter Helmert shift to WGS84 (S-JTSK to WGS 84, EPSG:1623's values). tools/geo.py uses ČÚZK's
// grid instead; against it this is within 0.14 m on 200 points across Prague (tools/test_geo_js.py): to open
// street-level imagery at a place, not for building data.
const D = Math.PI / 180, SEC = D / 3600;
const a = 6377397.155, f = 1 / 299.1528128, e2 = 2 * f - f * f, e = Math.sqrt(e2);
const phiC = (49 + 30 / 60) * D, lam0 = (24 + 50 / 60) * D, alphaC = (30 + 17 / 60 + 17.30311 / 3600) * D;
const phiP = 78.5 * D, kP = 0.9999;
const A = (a * Math.sqrt(1 - e2)) / (1 - e2 * Math.sin(phiC) ** 2);
const B = Math.sqrt(1 + (e2 * Math.cos(phiC) ** 4) / (1 - e2));
const g0 = Math.asin(Math.sin(phiC) / B);
const t0 = (Math.tan(Math.PI / 4 + g0 / 2) * ((1 + e * Math.sin(phiC)) / (1 - e * Math.sin(phiC))) ** ((e * B) / 2)) / Math.tan(Math.PI / 4 + phiC / 2) ** B;
const n = Math.sin(phiP), r0 = (kP * A) / Math.tan(phiP);
// S-JTSK → WGS 84 (position vector): dx, dy, dz m, rx, ry, rz arc seconds, scale ppm
const H = [570.8, 85.7, 462.8, 4.998 * SEC, 1.587 * SEC, 5.261 * SEC, 3.56e-6];
const WA = 6378137, WF = 1 / 298.257223563, We2 = 2 * WF - WF * WF;

// S-JTSK east, north (EPSG:5514, negative) → Bessel latitude, longitude (radians)
function krovakInverse(E, N) {
  const X = -N, Y = -E; // southing, westing
  const r = Math.hypot(X, Y), th = Math.atan2(Y, X), Dd = th / n;
  const T = 2 * (Math.atan((r0 / r) ** (1 / n) * Math.tan(Math.PI / 4 + phiP / 2)) - Math.PI / 4);
  const U = Math.asin(Math.cos(alphaC) * Math.sin(T) - Math.sin(alphaC) * Math.cos(T) * Math.cos(Dd));
  const V = Math.asin((Math.cos(T) * Math.sin(Dd)) / Math.cos(U));
  let phi = U;
  for (let i = 0; i < 6; i++) {
    phi = 2 * (Math.atan(t0 ** (-1 / B) * Math.tan(U / 2 + Math.PI / 4) ** (1 / B) * ((1 + e * Math.sin(phi)) / (1 - e * Math.sin(phi))) ** (e / 2)) - Math.PI / 4);
  }
  return [phi, lam0 - V / B];
}

// game x, y (m) in the frame with S-JTSK origin [E0, N0] → [lat, lon] in degrees (WGS84); h: ellipsoidal
// height, 0 is fine for a position
export function toLatLon(x, y, origin, h = 0) {
  const [phi, lam] = krovakInverse(origin[0] + x, origin[1] + y);
  const nu = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
  const X = (nu + h) * Math.cos(phi) * Math.cos(lam), Y = (nu + h) * Math.cos(phi) * Math.sin(lam), Z = (nu * (1 - e2) + h) * Math.sin(phi);
  const [dx, dy, dz, rx, ry, rz, s] = H, m = 1 + s;
  const X2 = dx + m * (X - rz * Y + ry * Z), Y2 = dy + m * (rz * X + Y - rx * Z), Z2 = dz + m * (-ry * X + rx * Y + Z);
  const p = Math.hypot(X2, Y2);
  let lat = Math.atan2(Z2, p * (1 - We2));
  for (let i = 0; i < 5; i++) {
    const v = WA / Math.sqrt(1 - We2 * Math.sin(lat) ** 2);
    lat = Math.atan2(Z2 + We2 * v * Math.sin(lat), p);
  }
  return [lat / D, Math.atan2(Y2, X2) / D];
}
