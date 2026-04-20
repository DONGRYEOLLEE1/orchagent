/* Features, Architecture, Code, CTA, Tweaks panel */

const { useState: useState2, useEffect: useEffect2, useRef: useRef2 } = React;

function Features() {
  return (
    <section className="section" id="features">
      <div className="wrap">
        <div className="section-head">
          <h2 className="display">Observable by <em>default.</em></h2>
          <p className="desc">
            Every planning step, every tool call, every validator verdict, every checkpoint — stamped with a trace
            id and streamed back through SSE. Nothing happens off-camera.
          </p>
        </div>

        <div className="feat-grid">
          <div className="feat w-6">
            <span className="feat-index">01 / 06</span>
            <div className="feat-kicker">HIERARCHICAL ORCHESTRATION</div>
            <h3 className="display">Head delegates.<br/>Teams specialize.<br/>Workers execute.</h3>
            <p>One top-level supervisor routes intent to three team subgraphs — research, writing, vision — each with its own workers, tools, and validators. You compose behavior by editing a graph, not a prompt.</p>
            <div className="feat-visual">
              <div style={{display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8}}>
                <div className="mini-box"><span>HEAD</span><span style={{color: "var(--accent)"}}>supervisor</span></div>
                <div className="mini-box"><span>TEAM</span><span style={{color: "var(--accent)"}}>×3</span></div>
                <div className="mini-box"><span>WORKER</span><span style={{color: "var(--accent)"}}>×9+</span></div>
              </div>
            </div>
          </div>

          <div className="feat w-6">
            <span className="feat-index">02 / 06</span>
            <div className="feat-kicker">HITL · HUMAN-IN-THE-LOOP</div>
            <h3 className="display">Pause the graph.<br/>Ask the human.<br/>Resume the thread.</h3>
            <p>Head-level routing can interrupt for approval, rejection, or feedback — and pick up from the same checkpoint when you respond. Self-correction loops inside teams run silently.</p>
            <div className="feat-visual" style={{display: "flex", gap: 8, flexWrap: "wrap"}}>
              <span className="mini-box" style={{color: "var(--signal)", borderColor: "color-mix(in srgb, var(--signal) 40%, transparent)"}}>◆ interrupt</span>
              <span className="mini-box">approve</span>
              <span className="mini-box">reject</span>
              <span className="mini-box">feedback</span>
              <span className="mini-box">resume</span>
            </div>
          </div>

          <div className="feat w-4">
            <span className="feat-index">03 / 06</span>
            <div className="feat-kicker">SELF-CORRECTION</div>
            <h3 className="display">Validators loop.</h3>
            <p>Each team runs a validator after its worker. Failed outputs get routed back with correction feedback until they pass — or escalate.</p>
          </div>

          <div className="feat w-4">
            <span className="feat-index">04 / 06</span>
            <div className="feat-kicker">MULTIMODAL</div>
            <h3 className="display">Images route<br/>natively.</h3>
            <p>Text-with-image inputs jump to the vision team. Model-native VLM, metadata & resize tools, validated confidence — no glue code.</p>
          </div>

          <div className="feat w-4">
            <span className="feat-index">05 / 06</span>
            <div className="feat-kicker">TRACE PERSISTENCE</div>
            <h3 className="display">Replay every<br/>execution.</h3>
            <p>SQL-backed trace events plus <span className="mono" style={{color: "var(--fg-0)"}}>.jsonl</span> session logs. Step through any thread post-hoc.</p>
            <div className="feat-visual">
              <div className="bar-chart">
                {[0.3, 0.5, 0.4, 0.7, 0.55, 0.8, 0.6, 0.9, 0.75, 0.65, 0.95, 0.7, 0.85, 0.6].map((h, i) => (
                  <i key={i} style={{height: `${h*100}%`}}/>
                ))}
              </div>
            </div>
          </div>

          <div className="feat w-12">
            <span className="feat-index">06 / 06</span>
            <div className="feat-kicker">SSE EVENT CONTRACT</div>
            <h3 className="display">Six event types. One stream. <em>Zero</em> black boxes.</h3>
            <p style={{maxWidth: 640}}>
              Every execution emits a normalized stream: <span className="mono" style={{color: "var(--fg-0)"}}>status</span>, <span className="mono" style={{color: "var(--fg-0)"}}>route</span>, <span className="mono" style={{color: "var(--fg-0)"}}>reasoning</span>, <span className="mono" style={{color: "var(--fg-0)"}}>tool</span>, <span className="mono" style={{color: "var(--fg-0)"}}>text</span>, <span className="mono" style={{color: "var(--fg-0)"}}>checkpoint</span>. Parser and contract live in <span className="mono" style={{color: "var(--fg-0)"}}>chat-stream.test.mjs</span> — build verification and SSE tests run in CI.
            </p>
            <div className="feat-visual" style={{marginTop: 28}}>
              <div style={{display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8}}>
                {[
                  ["STATUS","connecting → running → done"],
                  ["ROUTE","head → team → worker"],
                  ["REASONING","internal thought chunks"],
                  ["TOOL","name · args · result"],
                  ["TEXT","final synthesis chunks"],
                  ["CHECKPOINT","ckpt_id · resumable"],
                ].map(([k, v]) => (
                  <div key={k} style={{border: "1px solid var(--line-2)", padding: "12px 14px", borderRadius: 2, background: "var(--bg-1)"}}>
                    <div style={{fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--accent)", letterSpacing: "0.12em", marginBottom: 6}}>{k}</div>
                    <div style={{fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)", lineHeight: 1.5}}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Architecture() {
  const [hover, setHover] = useState2(null);
  return (
    <section className="section" id="architecture">
      <div className="wrap">
        <div className="section-head">
          <h2 className="display">
            The <em>graph</em>, in full.
          </h2>
          <p className="desc">
            This is the compiled LangGraph topology. Solid lines are synchronous edges, dotted lines are conditional
            handoffs, amber nodes validate, cyan nodes orchestrate.
          </p>
        </div>

        <div className="arch">
          {/* Row 1 — Head */}
          <div className="arch-row">
            <div className="arch-node supervisor" style={{minWidth: 260}}>
              <div className="arch-label">LEVEL 0 · ENTRY</div>
              <div className="arch-title">Head Supervisor</div>
              <div className="arch-desc">classifies intent · delegates · interrupts for HITL · synthesizes final answer</div>
            </div>
          </div>

          {/* Row 2 — Team supervisors */}
          <div className="arch-row">
            {[
              ["Research Supervisor", "tavily · scraper · validator", "research"],
              ["Writing Supervisor", "writer · noter · chart · validator", "writing"],
              ["Vision Supervisor", "analyst · meta · resize · validator", "vision"],
            ].map(([title, desc, id], i) => (
              <div key={id} className="arch-node supervisor" onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
                <div className="arch-connector active"></div>
                <div className="arch-label">LEVEL 1 · TEAM · {String(i+1).padStart(2,"0")}</div>
                <div className="arch-title">{title}</div>
                <div className="arch-desc">{desc}</div>
              </div>
            ))}
          </div>

          {/* Row 3 — Workers + validators */}
          <div className="arch-row">
            {[
              { title: "Tavily · Scraper", desc: "web retrieval · structured extraction", kind: "w" },
              { title: "Doc Writer · Note Taker · Chart Gen", desc: "structured drafting · svg artifacts", kind: "w" },
              { title: "Vision Analyst · Meta · Resize", desc: "model-native vlm · metadata tools", kind: "w" },
            ].map((n, i) => (
              <div key={i} className="arch-node">
                <div className="arch-connector"></div>
                <div className="arch-label">LEVEL 2 · WORKERS</div>
                <div className="arch-title">{n.title}</div>
                <div className="arch-desc">{n.desc}</div>
              </div>
            ))}
          </div>

          <div className="arch-row" style={{marginTop: 80}}>
            {[1,2,3].map(i => (
              <div key={i} className="arch-node validator">
                <div className="arch-connector" style={{background: "linear-gradient(to bottom, transparent, var(--signal))"}}></div>
                <div className="arch-label">LEVEL 2 · VALIDATOR</div>
                <div className="arch-title">Team Validator</div>
                <div className="arch-desc">self-correction loop · back-to-supervisor on failure</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function CodeSection() {
  return (
    <section className="section" id="integrate">
      <div className="wrap">
        <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 60, alignItems: "center"}}>
          <div>
            <div className="mono-eyebrow" style={{marginBottom: 24}}>QUICK START / 60 SECONDS</div>
            <h2 className="display" style={{fontSize: "clamp(42px, 5vw, 72px)", lineHeight: 1.0, letterSpacing: "-0.02em", margin: "0 0 24px"}}>
              Two commands.<br/>One <em style={{fontStyle: "italic", color: "var(--accent)"}}>graph.</em>
            </h2>
            <p style={{color: "var(--fg-2)", fontSize: 16, lineHeight: 1.6, marginBottom: 32}}>
              Python 3.12, FastAPI, LangGraph. Next.js 16 frontend. Docker Compose for the full stack, or run backend and
              frontend separately during development. Every layer — backend SSE contract, frontend parser, validator edge
              cases — ships with tests.
            </p>
            <div style={{display: "flex", gap: 12, flexWrap: "wrap"}}>
              <a className="btn btn-primary btn-arrow" href="https://github.com/DONGRYEOLLEE1/orchagent" target="_blank">Clone repo</a>
              <a className="btn btn-ghost" href="https://github.com/DONGRYEOLLEE1/orchagent#readme" target="_blank">Read docs</a>
            </div>
            <div style={{marginTop: 44, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20}}>
              <div>
                <div className="mono-eyebrow" style={{marginBottom: 6}}>STACK</div>
                <div style={{fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-1)", lineHeight: 1.8}}>
                  FastAPI · LangGraph<br/>
                  Next.js 16 · React<br/>
                  uv · Docker Compose
                </div>
              </div>
              <div>
                <div className="mono-eyebrow" style={{marginBottom: 6}}>LICENSE</div>
                <div style={{fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-1)", lineHeight: 1.8}}>
                  MIT<br/>
                  <span style={{color: "var(--fg-3)"}}>advanced prototype</span>
                </div>
              </div>
            </div>
          </div>

          <div className="code-block">
            <div className="code-head">
              <div className="dots"><i/><i/><i/></div>
              <span className="fname">~/orchagent $</span>
            </div>
            <div className="code-body">
              <pre>
                <span className="c"># 1. spin up the full stack</span>{"\n"}
                <span className="p">$</span> ./infra/scripts/start-dev.sh{"\n\n"}
                <span className="c"># 2. or run backend alone</span>{"\n"}
                <span className="p">$</span> cd apps/backend && uv sync{"\n"}
                <span className="p">$</span> uv run uvicorn main:app --reload --port <span className="s">8002</span>{"\n\n"}
                <span className="c"># open the workspace</span>{"\n"}
                <span className="p">→</span> <span className="f">http://localhost:3000</span>{"\n\n"}
                <span className="c"># run the test suite</span>{"\n"}
                <span className="p">$</span> uv run pytest tests/ -v{"\n"}
                <span className="p">→</span> <span className="k">91 passed</span> in <span className="s">12.4s</span>{"\n\n"}
                <span className="c"># stream from the API directly</span>{"\n"}
                <span className="p">$</span> curl -N <span className="f">http://localhost:8002/v1/stream</span>{"\n"}
                {"    -d "}<span className="s">{`'{"q":"compare frameworks"}'`}</span>{"\n"}
                <span className="p">←</span> <span className="k">event:</span> route    <span className="s">"head → research"</span>{"\n"}
                <span className="p">←</span> <span className="k">event:</span> tool     <span className="s">"tavily_search"</span>{"\n"}
                <span className="p">←</span> <span className="k">event:</span> text     <span className="s">"Compared four frameworks..."</span>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="section">
      <div className="wrap">
        <div className="cta-block">
          <div className="mono-eyebrow" style={{marginBottom: 24}}>READY WHEN YOU ARE</div>
          <h2>Ship agents you<br/>can <em>actually debug.</em></h2>
          <p>OrchAgent is an advanced prototype focused on orchestration, observability, and recovery. Read the code, run the stack, fork the graph.</p>
          <div className="cta-row">
            <a href="https://github.com/DONGRYEOLLEE1/orchagent" target="_blank" className="btn btn-primary btn-arrow">Open on GitHub</a>
            <a href="#demo" className="btn btn-ghost">Replay demo</a>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer-inner">
          <div style={{display: "flex", gap: 24, alignItems: "center"}}>
            <span className="logo"><span className="logo-mark"/>ORCH·AGENT</span>
            <span style={{color: "var(--fg-4)"}}>·</span>
            <span>v0.3 · main · b1e347e</span>
          </div>
          <div style={{display: "flex", gap: 20}}>
            <span>MIT LICENSE</span>
            <span style={{color: "var(--fg-4)"}}>·</span>
            <span>developed by DONGRYEOLLEE</span>
            <span style={{color: "var(--fg-4)"}}>·</span>
            <a href="https://github.com/DONGRYEOLLEE1/orchagent" target="_blank" style={{color: "var(--fg-2)", textDecoration: "none"}}>github ↗</a>
          </div>
        </div>
      </div>
    </footer>
  );
}

// =================== TWEAKS PANEL ===================
const ACCENTS = {
  cyan:   { primary: "oklch(0.82 0.14 200)", signal: "oklch(0.80 0.15 75)" },
  amber:  { primary: "oklch(0.80 0.15 75)",  signal: "oklch(0.78 0.15 200)" },
  violet: { primary: "oklch(0.72 0.17 295)", signal: "oklch(0.78 0.15 75)" },
  lime:   { primary: "oklch(0.86 0.20 130)", signal: "oklch(0.75 0.17 30)" },
};

function TweaksPanel({ tweaks, setTweaks, active, setActive }) {
  if (!active) return null;
  return (
    <div className="tweaks open">
      <h4>Tweaks <span>●</span></h4>
      <div className="tweak-group">
        <div className="tweak-label">Accent palette</div>
        <div className="swatch-row">
          {Object.keys(ACCENTS).map(k => (
            <button key={k} aria-label={k} title={k}
              onClick={() => setTweaks({...tweaks, accent: k})}
              className={`swatch ${tweaks.accent === k ? "active" : ""}`}
              style={{background: ACCENTS[k].primary}}/>
          ))}
        </div>
      </div>
      <div className="tweak-group">
        <div className="tweak-label">Hero scenario</div>
        <div className="tweak-options">
          {["research", "vision", "writing"].map(k => (
            <button key={k}
              className={`tweak-opt ${tweaks.scenario === k ? "active" : ""}`}
              onClick={() => setTweaks({...tweaks, scenario: k})}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <div className="tweak-group">
        <div className="tweak-label">Background density</div>
        <div className="tweak-options">
          {["subtle", "grid", "clean"].map(k => (
            <button key={k}
              className={`tweak-opt ${tweaks.bg === k ? "active" : ""}`}
              onClick={() => setTweaks({...tweaks, bg: k})}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <button onClick={() => setActive(false)} style={{
        marginTop: 14, width: "100%", padding: "6px 8px",
        background: "transparent", border: "1px solid var(--line-2)",
        color: "var(--fg-2)", fontFamily: "var(--font-mono)", fontSize: 10,
        letterSpacing: "0.08em", textTransform: "uppercase", cursor: "pointer",
        borderRadius: 2,
      }}>Close</button>
    </div>
  );
}

window.Features = Features;
window.Architecture = Architecture;
window.CodeSection = CodeSection;
window.CTA = CTA;
window.Footer = Footer;
window.TweaksPanel = TweaksPanel;
window.ACCENTS = ACCENTS;
