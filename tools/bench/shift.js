// SPDX-License-Identifier: AGPL-3.0-or-later
// Dev helper (not part of the game): a shift started from the menu, as the player starts it. src/main.js start()
// is async (it awaits the classic model and the figure font before it makes the game, since #383), so a bench
// waits for the new game: one read straight after the click is the previous game, or none (#400).
export async function startShift({ timeout = 30 } = {}) {
  const before = window.game;
  document.getElementById('btnStart').click();
  const t0 = performance.now();
  while (window.game === before || !window.game) {
    if (performance.now() - t0 > timeout * 1000) throw new Error(`the shift did not start within ${timeout} s`);
    await new Promise((r) => setTimeout(r, 20));
  }
  return window.game;
}
