"""Browser geometry tests; start python -I tools/serve.py 8743 first."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8743/README.md')
    print(page.evaluate('''async () => {
      const {Route}=await import('/src/route.js');
      const check=(ok,msg)=>{if(!ok) throw Error(msg);};
      const loop=new Route([[0,0],[100,0],[100,4],[0,4]]);
      const same=loop.nearestOnHeading(50,0,1,0), opposing=loop.nearestOnHeading(50,0,-1,0);
      check(same.d<0.1 && same.s<100,'same-direction leg');
      check(opposing.d>3.5 && opposing.d<4.5 && opposing.s>104,'opposing leg beyond nearer same-direction track');
      const single=new Route([[100,0],[0,0]]);
      check(single.nearestOnHeading(50,0,-1,0).d<0.1,'genuine shared opposing track');
      check(single.nearestOnHeading(50,0,1,0)===null,'no matching traversal');
      const crossing=new Route([[50,-50],[50,50]]);
      check(crossing.nearestOnHeading(50,0,1,0)===null,'perpendicular crossing');
      const repeated=new Route([[0,0],[100,0],[100,4],[0,4],[0,0],[100,0]]);
      check(repeated.nearestOnHeading(50,0,-1,0).s>100,'repeated same-direction traversals cannot mask opposing track');
      const merging=new Route([[0,0],[40,90]]);
      check(merging.nearestOnHeading(20,45,1,0)===null && merging.nearestOnHeading(20,45,1,0,0.3)!==null,'retain car-following heading tolerance');
      return '7 route-direction cases pass';
    }'''))
    browser.close()
