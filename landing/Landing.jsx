/* Landing page components — Hero + Demo console + Features + Arch + CTA + Tweaks */

const { useState, useEffect, useRef, useMemo } = React;

// ========= Hero orchestrator hook =========
function useOrchestration(scenarioId, running) {
  const scenario = Scenarios[scenarioId];
  const [currentStepIdx, setCurrentStepIdx] = useState(-1);
  const [events, setEvents] = useState([]);
  const timers = useRef([]);

  useEffect(() => {
    // cleanup on change
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setCurrentStepIdx(-1);
    setEvents([]);

    if (!running) return;

    scenario.steps.forEach((step, idx) => {
      const id = setTimeout(() => {
        setCurrentStepIdx(idx);
        setEvents(prev => [...prev, { ...step, idx, id: `${scenarioId}-${idx}-${Date.now()}` }].slice(-8));
      }, step.t);
      timers.current.push(id);
    });

    // Loop the scenario
    const totalDur = scenario.steps[scenario.steps.length - 1].t + 1800;
    const loopId = setTimeout(() => {
      setCurrentStepIdx(-1);
      setEvents([]);
    }, totalDur);
    timers.current.push(loopId);

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [scenarioId, running]);

  const active = currentStepIdx >= 0 ? scenario.steps[currentStepIdx] : null;
  return { active, events, scenario, currentStepIdx };
}

function fmtTs(offsetMs) {
  const base = new Date("2026-04-20T14:32:07Z").getTime();
  const d = new Date(base + offsetMs);
  return d.toISOString().slice(11, 19);
}

// ========= EventLog =========
function EventLog({ events, scenarioLabel }) {
  return (
    <div className="event-log">
      <div className="event-log-header">
        <span className="event-log-title">SSE · {scenarioLabel}</span>
        <span className="event-log-stream">STREAMING</span>
      </div>
      <div className="event-list">
        {events.length === 0 && (
          <div className="event-row">
            <span className="ts">{fmtTs(0)}</span>
            <span className="tag text">idle</span>
            <span className="msg">awaiting user message...</span>
          </div>
        )}
        {events.slice().reverse().map(e => (
          <div className="event-row" key={e.id}>
            <span className="ts">{fmtTs(e.t)}</span>
            <span className={`tag ${e.ev.toLowerCase() === "reason" ? "reason" : e.ev.toLowerCase() === "route" ? "route" : e.ev.toLowerCase() === "tool" ? "tool" : e.ev.toLowerCase() === "ckpt" ? "ckpt" : "text"}`}>
              {e.ev}
            </span>
            <span className="msg">{e.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ========= Hero section =========
function Hero({ scenarioId, setScenarioId }) {
  const [running, setRunning] = useState(true);
  const { active, events, scenario } = useOrchestration(scenarioId, running);

  return (
    <section className="section hero-section" style={{ padding: 0, borderTop: "none" }}>
      <div className="wrap">
        <div className="hero">
          <div className="hero-copy">
            <div className="hero-eyebrow">
              <span>ORCH·AGENT / v0.3 / HIERARCHICAL</span>
            </div>

            <h1 className="display">
              Orchestrate<br/>
              <em>agents</em> like<br/>
              a <span className="signal">mission</span><br/>
              control<span style={{color: "var(--accent)"}}>.</span>
            </h1>

            <p className="hero-sub">
              A hierarchical multi-agent platform routing requests through <em style={{color: "var(--fg-0)"}}>Head → Team → Worker</em>
              subgraphs. Reasoning, routing, tool activity, and checkpoints stream live — so you see the machine thinking,
              not just the answer.
            </p>

            <div className="hero-ctas">
              <a href="#demo" className="btn btn-primary btn-arrow">Run the demo</a>
              <a href="https://github.com/DONGRYEOLLEE1/orchagent" target="_blank" className="btn btn-ghost">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 005.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.93-.89-1.18-.89-1.18-.73-.5.05-.49.05-.49.8.06 1.23.83 1.23.83.72 1.23 1.88.88 2.34.67.07-.52.28-.88.51-1.08-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 014 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.74.54 1.48v2.2c0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
                GitHub
              </a>
            </div>

            <div className="hero-meta">
              <div className="hero-stat">
                <span className="v">03</span>
                <span className="l">Team subgraphs</span>
              </div>
              <div className="hero-stat">
                <span className="v">09</span>
                <span className="l">Worker agents</span>
              </div>
              <div className="hero-stat">
                <span className="v">SSE</span>
                <span className="l">Live streaming</span>
              </div>
              <div className="hero-stat">
                <span className="v">HITL</span>
                <span className="l">Interrupt/Resume</span>
              </div>
            </div>
          </div>

          <div className="hero-graph">
            <div className="corner-marks">
              <i/><i/><i/><i/>
            </div>
            <HeroGraph scenario={scenarioId} activeStep={active} />

            <EventLog events={events} scenarioLabel={scenario.label}/>
          </div>
        </div>
      </div>
    </section>
  );
}

// ========= Demo Console (interactive) =========
function DemoConsole({ scenarioId, setScenarioId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [activeScenario, setActiveScenario] = useState(null);
  const [currentStepIdx, setCurrentStepIdx] = useState(-1);
  const [awaitingHitl, setAwaitingHitl] = useState(false);
  const timers = useRef([]);

  const scenario = activeScenario ? Scenarios[activeScenario] : null;

  const runScenario = (id, customPrompt) => {
    // clear
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const sc = Scenarios[id];
    const prompt = customPrompt || sc.prompt;

    setMessages([{ role: "user", text: prompt, ts: fmtTs(0) }]);
    setActiveScenario(id);
    setCurrentStepIdx(-1);
    setAwaitingHitl(false);

    sc.steps.forEach((step, idx) => {
      const tid = setTimeout(() => {
        if (step.isHitl) {
          setCurrentStepIdx(idx);
          setAwaitingHitl(true);
        } else {
          setCurrentStepIdx(idx);
        }
      }, step.t);
      timers.current.push(tid);
    });

    const last = sc.steps[sc.steps.length - 1];
    const finalId = setTimeout(() => {
      setMessages(prev => [...prev, { role: "agent", text: sc.answer, agent: sc.agent, ts: fmtTs(last.t + 200) }]);
    }, last.t + 400);
    timers.current.push(finalId);
  };

  const handleHitl = (approve) => {
    setAwaitingHitl(false);
    if (!approve) {
      // short circuit
      timers.current.forEach(clearTimeout);
      setMessages(prev => [...prev, { role: "agent", text: "Rejected by operator. Thread paused at checkpoint.", agent: "head", ts: fmtTs(0) }]);
    }
  };

  useEffect(() => {
    // auto-run research on mount
    const t = setTimeout(() => runScenario("research"), 400);
    return () => {
      clearTimeout(t);
      timers.current.forEach(clearTimeout);
    };
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    // route by keyword
    const lower = input.toLowerCase();
    let target = "research";
    if (/image|photo|picture|vision|satellite|visual/.test(lower)) target = "vision";
    else if (/draft|write|brief|email|report|document/.test(lower)) target = "writing";
    runScenario(target, input);
    setInput("");
  };

  // visible tool cards & reasoning based on steps up to currentStepIdx
  const visibleSteps = scenario ? scenario.steps.slice(0, currentStepIdx + 1) : [];
  const toolSteps = visibleSteps.filter(s => s.ev === "TOOL");
  const reasoningSteps = visibleSteps.filter(s => s.ev === "REASON" || s.ev === "ROUTE" || s.ev === "CKPT");
  const latestToolIdx = toolSteps.length - 1;

  return (
    <section className="section" id="demo">
      <div className="wrap">
        <div className="section-head">
          <h2 className="display">
            Run a request.<br/>
            Watch the <em>graph</em> route it.
          </h2>
          <p className="desc">
            Send any prompt below. The router classifies intent, hands off to the matching team, the team dispatches workers
            and validators, and every event streams back through SSE. Try keywords like <span className="mono" style={{color: "var(--fg-0)"}}>image</span>, <span className="mono" style={{color: "var(--fg-0)"}}>draft</span>, or <span className="mono" style={{color: "var(--fg-0)"}}>research</span>.
          </p>
        </div>

        <div className="demo">
          {/* Chat column */}
          <div className="demo-col">
            <div className="demo-col-header">
              <span className="mono-eyebrow">CHAT · thread 7f3a91</span>
              <span className="tiny">ONLINE</span>
            </div>
            <div className="demo-col-body" style={{padding: "14px 16px"}}>
              <div className="chat-msgs">
                {messages.map((m, i) => (
                  <div key={i} className={`chat-row ${m.role}`}>
                    <div className="msg-meta">
                      {m.role === "user" ? (
                        <>
                          <span>YOU</span>
                          <span style={{color: "var(--fg-4)"}}>·</span>
                          <span>{m.ts}</span>
                        </>
                      ) : (
                        <>
                          <span className={`agent-tag ${m.agent === "vision" ? "signal" : ""}`}>{(m.agent || "HEAD").toUpperCase()} · AGENT</span>
                          <span style={{color: "var(--fg-4)"}}>·</span>
                          <span>{m.ts}</span>
                        </>
                      )}
                    </div>
                    <div className={`msg-bubble ${m.role}`}>{m.text}</div>
                  </div>
                ))}
                {awaitingHitl && (
                  <div className="hitl-card">
                    <div className="hitl-head">INTERRUPT · APPROVAL REQUIRED</div>
                    <div className="hitl-body">
                      Writing team requests tone approval before proceeding with the draft. Choose <strong>formal</strong> or <strong>punchy</strong> — or reject entirely.
                    </div>
                    <div className="hitl-actions">
                      <button className="hitl-btn primary" onClick={() => handleHitl(true)}>Approve · formal</button>
                      <button className="hitl-btn" onClick={() => handleHitl(true)}>Approve · punchy</button>
                      <button className="hitl-btn" onClick={() => handleHitl(false)}>Reject</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div className="suggestion-row">
              <button className="suggestion" onClick={() => runScenario("research", Scenarios.research.prompt)}>▸ research task</button>
              <button className="suggestion" onClick={() => runScenario("vision", Scenarios.vision.prompt)}>▸ vision task</button>
              <button className="suggestion" onClick={() => runScenario("writing", Scenarios.writing.prompt)}>▸ writing + HITL</button>
            </div>
            <form className="chat-input" onSubmit={handleSubmit}>
              <span style={{color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 13}}>▸</span>
              <input
                type="text"
                placeholder="Send a message to the orchestrator..."
                value={input}
                onChange={e => setInput(e.target.value)}
              />
              <button className="btn btn-ghost" type="submit" style={{padding: "6px 10px", fontSize: 10}}>SEND</button>
            </form>
          </div>

          {/* Middle: Reasoning + Timeline */}
          <div className="demo-col">
            <div className="demo-col-header">
              <span className="mono-eyebrow">REASONING & ROUTING</span>
              <span className="tiny">{scenario?.label ?? "—"}</span>
            </div>
            <div className="demo-col-body">
              <div className="stack">
                {reasoningSteps.length === 0 && (
                  <div className="reason-block" style={{opacity: 0.5}}>
                    <div className="reason-head">idle</div>
                    <div>Send a message to start the orchestration.</div>
                  </div>
                )}
                {reasoningSteps.map((s, i) => {
                  const isLatest = i === reasoningSteps.length - 1;
                  return (
                    <div key={i} className={`reason-block ${isLatest ? "active" : ""}`}>
                      <div className="reason-head">
                        {s.ev === "ROUTE" ? "→ ROUTE" : s.ev === "CKPT" ? "◆ CHECKPOINT" : "◇ REASON"}
                        <span style={{marginLeft: 10, color: "var(--fg-3)"}}>{s.node?.toUpperCase()}</span>
                      </div>
                      <div>{s.msg}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right: Tool activity */}
          <div className="demo-col">
            <div className="demo-col-header">
              <span className="mono-eyebrow">TOOL ACTIVITY</span>
              <span className="tiny">{toolSteps.length} CALLS</span>
            </div>
            <div className="demo-col-body">
              <div className="stack">
                {toolSteps.length === 0 && (
                  <div className="tool-card" style={{opacity: 0.5}}>
                    <div className="tool-card-head">
                      <span className="tool-card-name">—</span>
                      <span className="tool-card-status">idle</span>
                    </div>
                    <div className="tool-card-detail">no worker tools active</div>
                  </div>
                )}
                {toolSteps.map((s, i) => {
                  const isActive = i === latestToolIdx && !scenario?.steps.slice(currentStepIdx+1).every(x => x.ev !== "TOOL" || false);
                  const isLatest = i === latestToolIdx;
                  return (
                    <div key={i} className={`tool-card ${isLatest ? "active" : "done"}`}>
                      <div className="tool-card-head">
                        <span className="tool-card-name">{s.node}</span>
                        <span className="tool-card-status">{isLatest ? "running" : "complete"}</span>
                      </div>
                      <div className="tool-card-detail">{s.msg}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

window.Hero = Hero;
window.DemoConsole = DemoConsole;
