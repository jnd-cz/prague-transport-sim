# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install/decode the approved #590 pack; optionally compare TR37 step outputs to a git revision.

Usage: python -P -E tools/test_contactor_pack.py [--against origin/main]
Own free-port server, no world data needed. Checks the actual ZIP through the game's installer, hashes and
browser storage, all eight WAVs, and event playback. --against compares 20,000 deterministic equipment steps.
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
  const reports = await P.installUrl('/test-pack.zip');
  if (!reports[0]?.ok) throw Error(JSON.stringify(reports));
  const manifest = P.state.get('jnd.t2r6004').manifest;
  const {TramAudio} = await import('/src/audio.js'), a = new TramAudio();
  a.start(); a.setMuted(true); a.setActive(true);
  const pack = V.soundsFor(V.byId.get('t3h')); await a.usePack(pack);
  const decoded = [];
  for (const f of manifest.files.filter(f=>f.path.endsWith('.wav'))) {
    const buffer = await a.ctx.decodeAudioData(await (await fetch(pack.url(f.path))).arrayBuffer());
    decoded.push({file:f.path,channels:buffer.numberOfChannels,duration:buffer.duration});
  }
  a.trace = [];
  for (const e of ['bell','door.buzzer','lineContactor.close','lineContactor.open','door.open']) a.emit(e,{current:240});
  const trace = a.trace;
  await a.ctx.close();
  return {reports,decoded,trace};
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
            z.write(f, f.name)
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
            result = page.evaluate(CHECK)
            assert len(result['decoded']) == 8, result
            assert [x['by'] for x in result['trace']] == ['pack']*4+['built-in'],result
            if before:
                result['physics'] = page.evaluate(COMPARE)
            page.reload()
            restored = page.evaluate("""async () => {
              const V=await import('/src/vehicles.js'),P=await import('/src/packages.js');
              await V.loadRegistry(); await P.loadInstalled(); return V.soundsFor(V.byId.get('t3h'))?.id;
            }""")
            assert restored == 'jnd.t2r6004',restored
            result['restored'] = restored
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        server.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
