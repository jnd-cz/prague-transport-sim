"""Read-only sample of the actual browser Route.nearest and heading on all built lines."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8743/README.md')
    results = page.evaluate('''async () => {
      const { Route, extendAlongTracks } = await import('/src/route.js');
      const out = [];
      for (const line of [9, 17, 22, 23, 37]) {
        const data = await (await fetch(`/data/line${line}.json`)).json();
        const route = new Route(data.path, extendAlongTracks(data.tracks, data.path, 60));
        const back = new Route(data.pathBack);
        let near = 0, same = 0, opposite = 0, cross = 0, overlapSame = 0;
        const examples = [];
        for (let s = 50; s < route.length - 50; s += 100) {
          const p = route.at(s), n = back.nearest(p.x, p.y);
          if (!n || n.d >= 25) continue;
          near++;
          const a = route.heading(s, 3), b = back.heading(n.s, 3);
          const dot = a.hx * b.hx + a.hy * b.hy;
          if (dot > 0.5) {
            same++;
            if (n.d < 1.8) overlapSame++;
            if (examples.length < 3) examples.push({ s: Math.round(s), d: +n.d.toFixed(2), dot: +dot.toFixed(2) });
          } else if (dot < -0.5) opposite++;
          else cross++;
        }
        out.push({ line, near, same, opposite, cross, overlapSame, examples });
      }
      return out;
    }''')
    for result in results:
        print(result)
    browser.close()
