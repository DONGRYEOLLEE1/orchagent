# OrchAgent — Landing Page

Static landing page for [OrchAgent](https://github.com/DONGRYEOLLEE1/orchagent) — a hierarchical multi-agent platform. Pure HTML/CSS + React via Babel Standalone (no build step).

## 🚀 Deploy to Vercel (from this subfolder)

This landing page lives inside the main `orchagent` monorepo at `landing/`. To deploy **only** this folder:

### One-time setup

1. Push the `landing/` folder to `main` on GitHub (as part of the orchagent repo).
2. Go to [vercel.com/new](https://vercel.com/new) → **Import** the `orchagent` repo.
3. In the import screen:
   - **Framework Preset**: `Other`
   - **Root Directory**: `landing` ← important
   - **Build Command**: *(leave blank)*
   - **Output Directory**: `./`
   - **Install Command**: *(leave blank)*
4. Click **Deploy**. You'll get `<project-name>.vercel.app` in ~30s.

Every push to `main` that touches `landing/**` will auto-redeploy.

### Custom domain (optional)

Project Settings → **Domains** → Add `orchagent.dev` (or whatever you own) → follow the DNS instructions.

---

## 🧪 Local preview

No build step required. Any static file server works:

```bash
cd landing
python3 -m http.server 4000
# or
npx serve .
```

Open `http://localhost:4000`.

---

## 📁 Files

| File | Purpose |
|---|---|
| `index.html` | Entry point — loads fonts, styles, React, Babel, and component scripts |
| `styles.css` | All styling — tokens, layout, animations |
| `HeroGraph.jsx` | SVG orbital hierarchy graph (head → teams → workers) |
| `Scenarios.jsx` | Research / Vision / Writing orchestration timelines |
| `Landing.jsx` | Hero section + interactive demo console |
| `LandingSections.jsx` | Features grid, architecture diagram, code section, CTA, footer, Tweaks |
| `vercel.json` | Deploy config — caching headers, security headers |

---

## 🎨 Customize

Edit `TWEAK_DEFAULTS` in `index.html` (between the `EDITMODE-BEGIN` / `EDITMODE-END` markers) to change the default accent color, hero scenario, and background density.

```js
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "cyan",      // cyan | amber | violet | lime
  "scenario": "research",// research | vision | writing
  "bg": "subtle"         // subtle | grid | clean
}/*EDITMODE-END*/;
```

---

## License

MIT — same as the parent repo.
