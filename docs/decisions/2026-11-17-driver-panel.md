# The driver's panel after car 6921, and the cab's frame (#246)

Status: **accepted** with the maintainer's answers to the mock-up (2026-11-17), below.

The mock-up laid the cab of car 6921 out for the game (the maintainer's photos in `raw/reference/photos/user-cab/`, the
controls' sources in `docs/research/prazsketramvaje/t3-cab.md`): grey hammer paint is the tram, in its order with its
plates; dark glass is the game on it (the pedal bar, the helper lamps, the info screen, key hints). It asked six
questions; the answers:

1. **The cab's frame:** the real pillars, the view ending where the real window ends, the door's view on the right.
   The posts are drawn where the T3's are (src/t3simple.js `CAB`), seen from the eye, so they turn with
   the head; the head turns until the screen's edge reaches the cab window's end on the left and the front door's on
   the right (src/cabframe.js `lookLimits`: about 103° on a 16:9 screen, it was 75° both ways). The screen's ceiling
   band stays the roof over all of it: the eye is 0.13 m under the windows' top, and their wall over them filled the
   upper half of a side view.
2. **Controls the game doesn't simulate:** drawn and inert, a hover says so; the list of what to implement is #640.
3. **Labels:** English when the player chooses that language, the Czech accented letters displayed correctly. The
   plates follow the game's language (src/panel.js `C`); a plate's letters shrink where its
   words don't fit (the system's fonts differ). (#249: in the maintainer's Firefox at 3840 x 2008 the panel's text labels
   overflowed: the panel lays its letters out at 6-14 px and scales the band up whole, and a browser's minimum font size, its fonts setting,
   holds them larger, past their plates; reproduced in Firefox with 12 and 16 px. `fit` measures that minimum (`minFont`)
   and scales the labels' words, the helper lamps', the keys' hints, the knobs' marks, the info screen's and the
   timetable's back to the size they should have; `tools/test_panel.py` checks it in Firefox with 16 px.)
4. **The info screen as 6921's onboard computer:** kept for now.
5. **Tab folds the desktop panel to the compact strip:** yes, to be tried in testing; the panel scales up on larger
   displays. The band is 240 px high at a 900 px high window and scales with
   the window's height (and its width under 1640 px per 900).
6. **The phone's own buttons for VÝHYBKA and the heating cut-out:** open until tried; they are in the sheet for now.

And beyond the questions: the analog meters taller and wider (the whole panel may grow), their number labels
readable, and the zrychlovač lamp as LED dots arranged like a die's five. The meters are 66 × 108 px with a figure at every 100 A
and every 10 V; the strip grew from 180 px to 240.

The maintainer's next answers, on the draft (#641):

- **The ceiling band as the roof:** kept for now.
- **The eye:** where the real driver sits, somewhat left of centre, placed from the seat on the T3 drawing. The general arrangement's plan view
  (drawingdatabase.com `Tatra-T3-1.gif`, 20 mm a pixel, the drawing #427 measured the model from) has the seat 0.32 m left
  of the centre line, its backrest 1.44 m and its front edge 0.96 m behind the nose. The eye moved there (src/cabframe.js
  `EYE`: 0.32 m left, 1.2 m behind the nose) from the centre line 0.8 m behind the nose, about over the desk. Its height
  stays 2.39 m: the side view has no seat. From the seat the left windscreen post stands about 22° left of ahead and comes
  into the forward view; the head turns about 105° to the left window's end and 84° to the front door's (it was 103° both
  ways).
- **The meters:** rectangles, not curved surfaces in perspective. Flat from above, after the photo of 6921's: a tick every
  20 A with a long one every 100 A and figures every 200 A; a tick every 2 V and figures every 10 V; the pointer's dark
  blade comes in from the right (src/panel.js `meter`).
- **The phone's buttons:** to be tried later.

Then, on the same draft: the windscreen's divider thinner, with a rubber gasket stripe down its middle; and in the side
views the info overlay hid the panel's features.

- **The windscreen's posts** (where its panes meet) are 3 cm with the gasket's black stripe down their middle; they were
  6 cm, plain. The pillars between the windscreen's wrap and the cab window or the door stay as wide as the outside
  model has them (0.27 and 0.19 m).
- **The game's block over the side views:** with the head turned all the way, the band slides further left until the
  side's last plate (the sanding lever's on the wall, the timetable on the wing) ends 12 px before the block; the extra
  slide grows with the turn (src/panel.js `slide`). At 1600 × 900 and 1920 × 1200 they end 10–12 px before it; at
  1280 × 1024 and 2560 × 1080 they cleared it already.

After trying the merged build (same day, with a photo of 6921's cab):

- **The side views:** on the right the main window's end with rounded corners, a piece of frame, then the door, its top
  level with the windscreen's top frame; on the left the main window's end with rounded corners, the frame, the start of
  the side window with part of its pane on the driver's side, then the cab's back wall. The ceiling band stays the top of every opening: where a pillar's edge meets
  it, the opening's corner is rounded (0.08 m at the edge's distance), and the door's leaves reach up under it. The cab's
  rear wall stands where the general arrangement has it, 1.62 m behind the nose, across the cab window: the cab has the
  window's front 0.57 m. The head turns left until 7° of the rear wall show (89° at 16:9; it was 105°, to the window's
  end); the drawing's diagonal partition to the front door's jamb is left out, so the door stays in view.
- **The lamp strip:** the V lamp stands for Výstup (some trams label it so) and is tied to the request-stop button
  (znamení řidiči). V is labelled VÝSTUP and lights when a passenger presses the
  request: at a request stop somebody gets off at, from a point 20 m to 60 % of the way from the last stop until the
  doors open (src/panel.js `requested`; it was lit within 400 m of such a stop). The left and right arrows: green
  LEDs, a third shorter. The first red brake lamp is labelled Brzda I (BRZDY I since #249, like BRZDY II).
  The parts of the |O| symbol may stand side by side: the brake lamps' bars stand beside the ring.
- **The knobs:** rotary switches line up with their position labels, not at another angle. The heaters' labels stand round their knobs where the pointer stops (0–3 and 0 – ½ – 1 from
  lower left to lower right); the cams' handles have a pointer and stop at their marks; the knobs with no labels on
  the car stand square, up off and right on.
- **The mirror:** on top of everything but the menus (it was hidden most in the side views). The cab's frame leaves the mirror's picture out, and its frame is over the HUD
  (index.html `#mirror` z-index 6, under the panel's sheet and the menus).
- **V and the unlabelled knobs** (2026-11-18, after a Wikimedia Commons photo of a T3P's panel at Anděl): V, the open-door
  symbol, is two strokes apart, green; the unlabelled knobs follow the reference photos. On the maintainer's photos of 6921
  the knobs without labels stand up, but two: DVEŘE I turned right with the front door open (the doors' lamp dark), so
  the doors' switches are up closed and right open as the game had them; OSVĚTLENÍ, the outside lights, 45° right, its
  night position (the DPP textbook's T3R.P pages: "na „den“ - to je vlevo"). The game has no night yet and the photos
  were taken in the evening, so it stands at day, 45° left. The saloon's fluorescent lighting stands at the left,
  "předvolba" (ibid.). VYPÍNAČ ŘÍZENÍ's marks read 0 up, 2 right, its handle between them at 1; PŘEPÍNAČ OSVĚTLENÍ's
  plate is too dark on the photo to read its marks, so it has none and its handle stands diagonal as there.
- **Záchranná brzda:** the red button left of the ammeter, labelled Bezpečnostní spínač before, is ZÁCHRANNÁ BRZDA
  (EMERGENCY BRAKE).
- **The phone's controls:** the small screen's button overlay is to be overhauled: a tester suggested pedal-shaped
  buttons for power and brake instead of up and down arrows; VÝHYBKA is more useful than the heating cut-out; more
  automation on the small screen. The overhaul is #661.
