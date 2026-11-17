# The driver's panel after car 6921, and the cab's frame (#246)

Status: **accepted** with the user's answers to the mock-up (Claude Code session 2026-11-17), quoted below.

The mock-up laid the cab of car 6921 out for the game (the user's photos in `raw/reference/photos/user-cab/`, the
controls' sources in `docs/research/prazsketramvaje/t3-cab.md`): grey hammer paint is the tram, in its order with its
plates; dark glass is the game on it (the pedal bar, the helper lamps, the info screen, key hints). It asked six
questions; the answers:

1. **The cab's frame:** "I would keep real pillars and end the view where real window ends. Right side can have door
   view there." The posts are drawn where the T3's are (src/t3simple.js `CAB`), seen from the eye, so they turn with
   the head; the head turns until the screen's edge reaches the cab window's end on the left and the front door's on
   the right (src/cabframe.js `lookLimits`: about 103° on a 16:9 screen, it was 75° both ways). The screen's ceiling
   band stays the roof over all of it: the eye is 0.13 m under the windows' top, and their wall over them filled the
   upper half of a side view.
2. **Controls the game doesn't simulate:** "draw and keep them inert. List what needs to be implemented and create
   issue for it." Drawn and inert, a hover says so; the list is #640.
3. **Labels:** "we can have english labels when player chooses that language. Make sure the czech accented letters
   display correctly". The plates follow the game's language (src/panel.js `C`); a plate's letters shrink where its
   words don't fit (the system's fonts differ).
4. **The info screen as 6921's onboard computer:** "yes let's keep it for now".
5. **Tab folds the desktop panel to the compact strip:** "let's do this and I will try it when testing. Make sure the
   panel scales up on larger resolution displays." The band is 240 px high at a 900 px high window and scales with
   the window's height (and its width under 1640 px per 900).
6. **The phone's own buttons for VÝHYBKA and the heating cut-out:** "not sure, will have to try it first to see how
   it works." Open: they are in the sheet for now.

And beyond the questions: "make the analog meters, like the ammeter, a bit taller (the whole panel can be taller)
and make sure the number labels are visible, so it can be wider too, basically more readable. And fix zrychlovač
lamp: it should be led dots arranged like dice number 5." The meters are 66 × 108 px with a figure at every 100 A
and every 10 V; the strip grew from 180 px to 240.
