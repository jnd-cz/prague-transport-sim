// SPDX-License-Identifier: AGPL-3.0-or-later
// A set of cars on the track (src/models.js placeConsist): each car placed by its type's running gear
// (src/articulated.js: the T3 one section on two bogie pivots), hung on the coupling, and its running gear
// posed from the track. A car with moving gear carries it as car.userData.gear (src/rigged.js, src/t3simple.js):
//   axle      half the wheelbase
//   pinY      the coupler pins' height in the car
//   live()    whether the gear is drawn now (the hybrid's lighter level has it merged)
//   turn(i, yaw)   bogie i (0 the front, 1 the rear) turned against the body about its pivot (+ to the left)
//   roll(s)        the wheels after s m along the track
//   swing(i, dir)  coupler i (0 the front, 1 the rear) pointing along dir, a unit vector in the car's frame
//                  (x left, y up, z forward) from its pin outwards; null: straight ahead
//   done()         after a car's calls (optional)
import * as THREE from 'three';
import { T3, CAR_PITCH } from './tram.js';
import { placeUnit } from './articulated.js';

const v3 = () => new THREE.Vector3();
const A = v3(), B = v3(), F = v3(), Q = v3(), qi = new THREE.Quaternion();

// A section's node at its pose from placeUnit (route x, y and height; lift: its origin over the track bed)
export function poseSection(node, p, lift = 0) {
  node.position.set(p.p[0], p.p[2] + lift, -p.p[1]);
  node.rotation.y = p.yaw;
  node.rotation.x = -p.pitch;
  node.rotation.z = -p.roll;
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
  const { cars } = model.userData, type = T3, pin = T3.couplerPivot, link = pitch - 2 * pin;
  const y = cars[0].userData.gear?.pinY ?? 0; // (the link runs between the pins)
  const poses = [];
  let f = sFront;
  const place = (car, front) => { const p = placeUnit(type, front, at); poseSection(car, p.sections[0]); return p; };
  cars.forEach((car, k) => {
    if (k > 0) {
      const prev = cars[k - 1];
      carPoint(prev, 0, y, -pin, A);
      // the next car's front along the track: two secant steps from the straight-track pitch
      let f2 = f - pitch;
      for (let i = 0; i < 3; i++) {
        place(car, f2);
        carPoint(car, 0, y, pin, B);
        const err = A.distanceTo(B) - link;
        if (Math.abs(err) < 1e-4) break;
        f2 += err;
      }
      f = f2;
    }
    poses.push(place(car, f));
  });
  // (each car's pose with its bogies' and joints' angles and what a limit held, for the debug overlay and window.game)
  model.userData.placed = poses;
  cars.forEach((car, k) => {
    const g = car.userData.gear;
    if (!g || !g.live()) return;
    poses[k].bogies.forEach((b, i) => g.turn(i, b.yaw));
    g.roll(sFront);
    // from this car's rear pin to the next one's front pin; the bar ahead from the previous car's rear pin
    const next = cars[k + 1], prev = cars[k - 1];
    if (next) { carPoint(car, 0, y, -pin, A); carPoint(next, 0, y, pin, B); g.swing(1, intoCar(car, F.subVectors(B, A).normalize(), Q)); } else g.swing(1, null);
    if (prev) { carPoint(prev, 0, y, -pin, A); carPoint(car, 0, y, pin, B); g.swing(0, intoCar(car, F.subVectors(A, B).normalize(), Q)); } else g.swing(0, null);
    g.done?.();
  });
}
