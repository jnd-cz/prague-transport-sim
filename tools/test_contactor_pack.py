# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shipped T2R 6004 pack (#590, #636): decode and play; optionally compare TR37 step outputs to a git revision.

Usage: python -P -E tools/test_contactor_pack.py [--against origin/main]
Own free-port server, no world data needed. The pack is listed in assets/vehicles.json and the game loads it; the
hybrid sounds with it only when it is picked (the default: the built-in sounds). All its Ogg Opus files, their MP3
fallbacks and the WAV masters decode; its events play by the pack; where the browser cannot decode the Ogg files
(served broken here), each event plays its MP3 fallback, as long as the Ogg. Its zip offered as a package is refused (the id is the game's own). --against compares
20,000 deterministic equipment steps.
"""
import argparse
import faulthandler
import functools
import http.server
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import threading
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import gpu  # noqa: E402

CHECK = """async () => {
  const V = await import('/src/vehicles.js'), P = await import('/src/packages.js');
  await V.loadRegistry();
  const t3h = V.byId.get('t3h'), manifest = V.soundPacks.get('jnd.t2r6004');
  if (!manifest) throw Error('the shipped pack is not loaded: ' + [...V.soundPacks.keys()]);
  const out = { offered: V.soundPacksFor(t3h).map((p) => p.id), byDefault: V.soundsFor(t3h)?.id ?? null };
  const {TramAudio} = await import('/src/audio.js');
  const play = async (url) => {
    const a = new TramAudio();
    a.start(); a.setMuted(true); a.setActive(true);
    const pack = V.soundsFor(t3h, 'jnd.t2r6004');
    await a.usePack(pack, url ? (f) => url(f, pack) : undefined);
    a.trace = [];
    for (const e of ['bell','door.buzzer','lineContactor.close','lineContactor.open','door.open']) a.emit(e,{current:240});
    const r = { trace: a.trace.map((x) => x.by), fellBack: a.fellBack, events: Object.fromEntries([...a.pack.events].map(([e, b]) => [e, b.map((x) => +x.duration.toFixed(3))])) };
    const decoded = [];
    for (const f of manifest.files.filter((f) => ['wav', 'ogg', 'mp3'].includes(f.path.split('.').pop()))) {
      const b = await a.ctx.decodeAudioData(await (await fetch(pack.url(f.path))).arrayBuffer());
      decoded.push({ file: f.path, channels: b.numberOfChannels, duration: +b.duration.toFixed(3) });
    }
    await a.ctx.close();
    return { ...r, decoded };
  };
  out.ogg = await play();
  // a browser without Opus: the Ogg files answer bytes it cannot decode
  out.asked = [];
  out.fallback = await play((f, pack) => { out.asked.push(f); return f.endsWith('.ogg') ? '/__undecodable.ogg' : pack.url(f); });
  out.refused = (await P.installUrl('/test-pack.zip'))[0];
  return out;
}"""

COMPARE = """async () => {
  const {TR37} = await import('/src/tr37.js'), {TR37:Before} = await import('/before-tr37.js');
  const a = new TR37(2), b = new Before(2);
  a.mode = b.mode = 'advanced'; a.park(false); b.park(false);
  let transitions = 0; a.onLineContactor = () => transitions++;
  for (let i=0;i<20000;i++) {
    if (i%137===0) { const s=[5,1,0,-3,4,-6,0,2][Math.floor(i/137)%8]; a.pressTo(s); b.pressTo(s); }
    const ctx={v:15*Math.abs(Math.sin(i/700)),voltage:550+100*Math.sin(i/190),doorsOpen:i%1700<20,
      rescue:i%2300<10,forcedStop:i%3300<10}, dt=[.01,.02,1/30][i%3];
    const x=a.update(dt,ctx),y=b.update(dt,ctx);
    if(JSON.stringify(x)!==JSON.stringify(y)) throw Error('equipment output differs at step '+i);
    for(const key of Object.keys(b)) if(JSON.stringify(a[key])!==JSON.stringify(b[key])) throw Error('equipment state '+key+' differs at step '+i);
  }
  return {steps:20000,transitions,output:'identical',state:'identical'};
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--against')
    args = ap.parse_args()
    faulthandler.dump_traceback_later(180, exit=True)
    folder = ROOT/'assets/jnd.t2r6004'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.iterdir()):
            z.write(f, 'package.json' if f.name == 'sounds.json' else f.name)
    before = None
    if args.against:
        before = subprocess.check_output(['git','show',f'{args.against}:src/tr37.js'],cwd=ROOT).decode('utf-8')
        before = before.replace("'./electric.js'", "'/src/electric.js'")
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            page = browser.new_page()
            imports = re.search(r'<script type="importmap">.*?</script>', (ROOT/'index.html').read_text(encoding='utf-8'), re.S).group()
            page.route('**/check.html',lambda r:r.fulfill(body='<html>'+imports+'</html>',content_type='text/html'))
            page.route('**/test-pack.zip',lambda r:r.fulfill(body=buf.getvalue(),content_type='application/zip'))
            if before:
                page.route('**/before-tr37.js',lambda r:r.fulfill(body=before,content_type='text/javascript'))
            page.goto(f'http://127.0.0.1:{server.server_port}/check.html')
            page.route('**/__undecodable.ogg',lambda r:r.fulfill(body=b'OggS' + bytes(200),content_type='audio/ogg'))
            result = page.evaluate(CHECK)
            assert result['offered'] == ['jnd.t2r6004'] and result['byDefault'] is None, result
            oggs = sum(f.endswith('.ogg') for f in json.load(open(folder/'sounds.json',encoding='utf-8'))['events'].values() for f in ([f] if isinstance(f,str) else f))
            for how in ('ogg', 'fallback'):
                r = result[how]
                assert r['trace'] == ['pack']*4+['built-in'], (how, r['trace'])
                assert len(r['decoded']) == 18, (how, r['decoded'])
            assert result['ogg']['fellBack'] == [] and len(result['fallback']['fellBack']) == 5 == oggs, result
            fetched = sorted(f for f in result['asked'] if not f.endswith('.ogg'))
            assert fetched == sorted(f[:-4] + '.mp3' for f in result['fallback']['fellBack']), result['asked']
            assert result['ogg']['events'] == result['fallback']['events'], (result['ogg']['events'], result['fallback']['events'])
            assert not result['refused']['ok'] and any('taken by the game' in x for x in result['refused']['problems']), result['refused']
            if before:
                result['physics'] = page.evaluate(COMPARE)
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        server.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
