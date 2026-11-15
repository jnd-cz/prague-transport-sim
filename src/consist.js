// SPDX-License-Identifier: AGPL-3.0-or-later
// A set of cars on the track (src/models.js placeConsist): each car on its two bogie pivots, hung on the
// coupling, and its running gear posed from the track. A car with moving gear carries it as
// car.userData.gear (src/rigged.js, src/t3simple.js):
//   axle      half the wheelbase: a bogie turns to the chord between its axles' points on the track
//   pinY      the coupler pins' height in the car
//   live()    whether the gear is drawn now (the hybrid's lighter level has it merged)
//   turn(i, yaw)   bogie i (0 the front, 1 the rear) turned against the body about its pivot (+ to the left)
//   roll(s)        the wheels after s m along the track
//   swing(i, dir)  coupler i (0 the front, 1 the rear) pointing along dir, a unit vector in the car's frame
//                  (x left, y up, z forward) from its pin outwards; null: straight ahead
//   done()         after a car's calls (optional)
import * as THREE from 'three';
import { T3, CAR_PITCH } from './tram.js';

const v3 = () => new THREE.Vector3();
const A = v3(), B = v3(), F = v3(), Q = v3(), qi = new THREE.Quaternion();

// A car's pose from the track: on its two bogie pivots, its centre c (at(s) -> [x, y, height, roll])
function placeCar(car, c, at, bogie) {
  const [ax, ay, za, ra = 0] = at(c + bogie), [bx, by, zb, rb = 0] = at(c - bogie);
  car.position.set((ax + bx) / 2, (za + zb) / 2, -(ay + by) / 2);
  car.rotation.y = Math.atan2(ax - bx, -(ay - by));
  car.rotation.x = -Math.atan2(za - zb, 2 * bogie);
  car.rotation.z = -(ra + rb) / 2;
}

// a bogie's yaw against its car: the chord between its axles' points on the track, its pivot at s
function bogieYaw(car, s, at, axle) {
  const [px, py] = at(s + axle), [qx, qy] = at(s - axle);
  const d = Math.atan2(px - qx, -(py - qy)) - car.rotation.y;
  return Math.atan2(Math.sin(d), Math.cos(d));
}

// a point of a car in world coordinates from its local (x left, y up, z forward)
const carPoint = (car, x, y, z, out) => { car.updateMatrix(); return out.set(x, y, z).applyMatrix4(car.matrix); };
// a world direction into a car's frame
const intoCar = (car, d, out) => out.copy(d).applyQuaternion(qi.copy(car.quaternion).invert());

// Each car of a set on the track. The first stands with its front coupler face at sFront; each next one
// hangs on the coupling: the two coupled bars are one stiff link from pin to pin (the Prague head's two
// pins, #248), so the next car stands where its front pin is that link's length from the car ahead's rear
// pin, a few cm closer along the track in a curve than on the straight. Then each car's gear: the bogies
// turned to the track, the wheels rolled by sFront, the coupled bars along the link, the free ones straight.
export function hangConsist(model, sFront, at, pitch = CAR_PITCH) {
  const { cars, bogie } = model.userData, pin = T3.couplerPivot, link = pitch - 2 * pin;
  const y = cars[0].userData.gear?.pinY ?? 0; // (the link runs between the pins)
  const centres = [];
  let c = sFront - T3.length / 2;
  cars.forEach((car, k) => {
    if (k > 0) {
      const prev = cars[k - 1];
      carPoint(prev, 0, y, -pin, A);
      // the next car's centre along the track: two secant steps from the straight-track pitch
      let c2 = c - pitch;
      for (let i = 0; i < 3; i++) {
        placeCar(car, c2, at, bogie);
        carPoint(car, 0, y, pin, B);
        const err = A.distanceTo(B) - link;
        if (Math.abs(err) < 1e-4) break;
        c2 += err;
      }
      c = c2;
    }
    placeCar(car, c, at, bogie);
    centres.push(c);
  });
  cars.forEach((car, k) => {
    const g = car.userData.gear;
    if (!g || !g.live()) return;
    g.turn(0, bogieYaw(car, centres[k] + bogie, at, g.axle));
    g.turn(1, bogieYaw(car, centres[k] - bogie, at, g.axle));
    g.roll(sFront);
    // from this car's rear pin to the next one's front pin; the bar ahead from the previous car's rear pin
    const next = cars[k + 1], prev = cars[k - 1];
    if (next) { carPoint(car, 0, y, -pin, A); carPoint(next, 0, y, pin, B); g.swing(1, intoCar(car, F.subVectors(B, A).normalize(), Q)); } else g.swing(1, null);
    if (prev) { carPoint(prev, 0, y, -pin, A); carPoint(car, 0, y, pin, B); g.swing(0, intoCar(car, F.subVectors(A, B).normalize(), Q)); } else g.swing(0, null);
    g.done?.();
  });
}
