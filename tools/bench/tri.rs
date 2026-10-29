// Benchmark kernel (not part of the game): the DTM lookup's triangle test, as in PERF-ANALYSIS §9,
// over the same flat arrays as the JS "flat" variant. Build:
// rustc --target wasm32-unknown-unknown --crate-type cdylib -O -C panic=abort tri.rs -o tri.wasm
// (add -C target-feature=+simd128 for the SIMD build)

// 8-byte aligned memory for the JS side to fill (Float64Array views need it)
#[no_mangle]
pub extern "C" fn alloc(bytes: usize) -> *mut f64 {
    let mut v = Vec::<f64>::with_capacity(bytes / 8 + 1);
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

// f: triangles, 9 doubles each; ids / start: the cells' triangle numbers (CSR); cells: each point's
// cell or -1; p: the points (x, y). Returns the sum of the hit heights (to compare with JS).
#[no_mangle]
pub unsafe extern "C" fn run(f: *const f64, ids: *const i32, start: *const i32, cells: *const i32, n: usize, p: *const f64) -> f64 {
    let mut s = 0.0;
    for i in 0..n {
        let k = *cells.add(i);
        if k < 0 {
            continue;
        }
        let (x, y) = (*p.add(i * 2), *p.add(i * 2 + 1));
        let (a, e) = (*start.add(k as usize) as usize, *start.add(k as usize + 1) as usize);
        for m in a..e {
            let o = *ids.add(m) as usize * 9;
            let t = std::slice::from_raw_parts(f.add(o), 9);
            let (px, py, pz, qx, qy, qz, rx, ry, rz) = (t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8]);
            let d = (qy - ry) * (px - rx) + (rx - qx) * (py - ry);
            if d.abs() < 1e-9 {
                continue;
            }
            let w1 = ((qy - ry) * (x - rx) + (rx - qx) * (y - ry)) / d;
            let w2 = ((ry - py) * (x - rx) + (px - rx) * (y - ry)) / d;
            let w3 = 1.0 - w1 - w2;
            if w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6 {
                continue;
            }
            s += w1 * pz + w2 * qz + w3 * rz;
        }
    }
    s
}
