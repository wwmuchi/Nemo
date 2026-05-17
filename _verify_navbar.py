"""Measure the .homebar position and styling on each page so we can detect any jumps."""
from playwright.sync_api import sync_playwright

URLS = [
    ("probe",   "http://127.0.0.1:5050/"),
    ("compass", "http://127.0.0.1:5050/compass/"),
    ("scores",  "http://127.0.0.1:5050/scores/"),
]

EVAL = """() => {
  const nav = document.querySelector('.homebar');
  if (!nav) return { error: 'no .homebar' };
  const r = nav.getBoundingClientRect();
  const cs = getComputedStyle(nav);

  const brand = nav.querySelector('.homebar-brand');
  const brandRect = brand ? brand.getBoundingClientRect() : null;

  const links = [...nav.querySelectorAll('.homebar-nav a')].map(a => {
    const lr = a.getBoundingClientRect();
    return { text: a.textContent.trim(), top: lr.top, left: lr.left, w: lr.width, h: lr.height };
  });

  return {
    nav: {
      top: r.top, left: r.left, width: r.width, height: r.height,
      position: cs.position,
      background: cs.backgroundColor,
      paddingTop: cs.paddingTop, paddingBottom: cs.paddingBottom,
      paddingLeft: cs.paddingLeft, paddingRight: cs.paddingRight,
      borderBottom: cs.borderBottomWidth + ' ' + cs.borderBottomColor,
      zIndex: cs.zIndex,
    },
    brand: brandRect && { top: brandRect.top, left: brandRect.left, h: brandRect.height },
    links,
  };
}"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    results = {}
    for name, url in URLS:
        page.goto(url, wait_until='networkidle')
        results[name] = page.evaluate(EVAL)
    browser.close()

# Print a compact comparison table.
print(f"{'page':<8} {'top':>6} {'left':>6} {'width':>7} {'height':>7}  {'pos':<8} {'pad-tb':<10} bg")
for name, r in results.items():
    n = r['nav']
    print(f"{name:<8} {n['top']:>6.1f} {n['left']:>6.1f} {n['width']:>7.1f} {n['height']:>7.1f}  "
          f"{n['position']:<8} {n['paddingTop']}/{n['paddingBottom']:<6} {n['background']}")

print()
print("Brand position:")
for name, r in results.items():
    b = r['brand']
    print(f"  {name:<8} top={b['top']:.1f} left={b['left']:.1f} h={b['h']:.1f}")

print()
print("Link positions (text, top, left, width):")
for name, r in results.items():
    print(f"  {name}:")
    for lk in r['links']:
        print(f"    {lk['text']:<10} top={lk['top']:.1f} left={lk['left']:.1f} w={lk['w']:.1f} h={lk['h']:.1f}")

# Pixel-perfect drift check between probe and compass, probe and scores.
print()
print("DRIFT vs probe (Δtop, Δheight, Δlink-left):")
probe = results['probe']
for name in ['compass', 'scores']:
    o = results[name]
    dtop = o['nav']['top'] - probe['nav']['top']
    dh = o['nav']['height'] - probe['nav']['height']
    # link drift: compare the "Probe" link's left position
    p_link = next((l for l in probe['links'] if l['text'] == 'Probe'), None)
    o_link = next((l for l in o['links']   if l['text'] == 'Probe'), None)
    dleft = (o_link['left'] - p_link['left']) if (p_link and o_link) else None
    print(f"  {name}: Δtop={dtop:+.1f}  Δheight={dh:+.1f}  ΔProbe-left={dleft:+.1f}")
