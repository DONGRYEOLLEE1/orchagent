/* Hero orbital graph — Head Supervisor at center, teams orbit, workers further out */

const HeroGraph = (() => {
  const { useRef, useEffect, useState, useMemo } = React;

  // Layout: center at (300, 300) of a 600x600 viewBox
  const CX = 300, CY = 300;
  const R_TEAM = 135;   // team ring radius
  const R_WORKER = 230; // worker ring radius

  const HEAD = { id: "head", label: "HEAD", role: "supervisor", x: CX, y: CY };

  // Teams at 120° intervals
  const TEAMS = [
    { id: "research", label: "RESEARCH", role: "team supervisor", angle: -90 },
    { id: "writing",  label: "WRITING",  role: "team supervisor", angle: 30 },
    { id: "vision",   label: "VISION",   role: "team supervisor", angle: 150 },
  ].map(t => ({
    ...t,
    x: CX + R_TEAM * Math.cos((t.angle * Math.PI) / 180),
    y: CY + R_TEAM * Math.sin((t.angle * Math.PI) / 180),
  }));

  // Workers per team (2-3 each)
  const WORKERS_DEF = {
    research: [
      { id: "tavily",  label: "TAVILY",  role: "search",    offset: -22 },
      { id: "scraper", label: "SCRAPER", role: "web",       offset: 0   },
      { id: "rval",    label: "VALID·R", role: "validator", offset: 22  },
    ],
    writing: [
      { id: "writer",  label: "WRITER",  role: "doc",       offset: -22 },
      { id: "noter",   label: "NOTES",   role: "taker",     offset: 0   },
      { id: "chart",   label: "CHARTS",  role: "gen",       offset: 22  },
    ],
    vision: [
      { id: "vana",    label: "ANALYST", role: "vlm",       offset: -18 },
      { id: "vtools",  label: "META",    role: "resize",    offset: 0   },
      { id: "vval",    label: "VALID·V", role: "validator", offset: 18  },
    ],
  };

  const WORKERS = [];
  TEAMS.forEach(team => {
    WORKERS_DEF[team.id].forEach(w => {
      const angle = team.angle + w.offset;
      WORKERS.push({
        ...w,
        teamId: team.id,
        angle,
        x: CX + R_WORKER * Math.cos((angle * Math.PI) / 180),
        y: CY + R_WORKER * Math.sin((angle * Math.PI) / 180),
      });
    });
  });

  const ALL_NODES = { head: HEAD, ...Object.fromEntries(TEAMS.map(t => [t.id, t])), ...Object.fromEntries(WORKERS.map(w => [w.id, w])) };

  // Edges
  const EDGES = [
    ...TEAMS.map(t => ({ from: "head", to: t.id })),
    ...WORKERS.map(w => ({ from: w.teamId, to: w.id })),
  ];

  function HeroGraph({ scenario, activeStep }) {
    // activeStep is { nodes: [ids], edges: [[from,to]...], signal: bool }
    const active = new Set(activeStep?.nodes ?? []);
    const signal = activeStep?.signal;

    const activeEdges = new Set((activeStep?.edges ?? []).map(([a,b]) => `${a}->${b}`));

    // Particles: one per active edge
    const particles = (activeStep?.edges ?? []).map(([from, to], idx) => {
      const a = ALL_NODES[from], b = ALL_NODES[to];
      return { id: `${from}-${to}-${idx}`, from: a, to: b };
    });

    return (
      <svg className="graph-svg" viewBox="0 0 600 600">
        <defs>
          <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0"/>
          </radialGradient>
        </defs>

        {/* Rings */}
        <circle className="graph-ring graph-ring-2" cx={CX} cy={CY} r={R_WORKER}/>
        <circle className="graph-ring" cx={CX} cy={CY} r={R_TEAM}/>
        <circle className="graph-ring graph-ring-2" cx={CX} cy={CY} r={60}/>

        {/* Rotating tick marks */}
        <g className="orbit-ticks">
          {Array.from({length: 48}).map((_, i) => {
            const a = (i * 360 / 48) * Math.PI / 180;
            const r1 = R_WORKER + 6;
            const r2 = R_WORKER + (i % 6 === 0 ? 16 : 10);
            return (
              <line key={i}
                x1={CX + r1*Math.cos(a)} y1={CY + r1*Math.sin(a)}
                x2={CX + r2*Math.cos(a)} y2={CY + r2*Math.sin(a)}
                stroke="var(--line-2)" strokeWidth="1"/>
            );
          })}
        </g>
        <g className="orbit-ticks-inner">
          {Array.from({length: 24}).map((_, i) => {
            const a = (i * 360 / 24) * Math.PI / 180;
            const r1 = R_TEAM - 6;
            const r2 = R_TEAM - (i % 4 === 0 ? 14 : 9);
            return (
              <line key={i}
                x1={CX + r1*Math.cos(a)} y1={CY + r1*Math.sin(a)}
                x2={CX + r2*Math.cos(a)} y2={CY + r2*Math.sin(a)}
                stroke="var(--line-1)" strokeWidth="1"/>
            );
          })}
        </g>

        {/* Degree marks on outer ring */}
        {[0, 90, 180, 270].map((deg, i) => {
          const a = (deg - 90) * Math.PI / 180;
          const r = R_WORKER + 28;
          return (
            <text key={i}
              x={CX + r*Math.cos(a)} y={CY + r*Math.sin(a)}
              fontFamily="var(--font-mono)" fontSize="8" fill="var(--fg-3)"
              textAnchor="middle" dominantBaseline="middle"
              letterSpacing="0.1em">
              {String(deg).padStart(3, "0")}°
            </text>
          );
        })}

        {/* Edges */}
        {EDGES.map((e, i) => {
          const from = ALL_NODES[e.from];
          const to = ALL_NODES[e.to];
          const key = `${e.from}->${e.to}`;
          const isActive = activeEdges.has(key);
          return (
            <line key={i}
              x1={from.x} y1={from.y}
              x2={to.x} y2={to.y}
              className={`graph-edge ${isActive ? (signal ? "signal" : "active") : ""}`}
            />
          );
        })}

        {/* Workers */}
        {WORKERS.map(n => {
          const isActive = active.has(n.id);
          return (
            <g key={n.id} className={`graph-node ${isActive ? (signal ? "signal" : "active") : ""}`}>
              <circle className="bg" cx={n.x} cy={n.y} r={18}/>
              {isActive && (
                <circle cx={n.x} cy={n.y} r={20} fill="none"
                  stroke={signal ? "var(--signal)" : "var(--accent)"} strokeWidth="1" opacity="0.5">
                  <animate attributeName="r" from="18" to="40" dur="1.6s" repeatCount="indefinite"/>
                  <animate attributeName="opacity" from="0.8" to="0" dur="1.6s" repeatCount="indefinite"/>
                </circle>
              )}
              <text className="label" x={n.x} y={n.y - 1} textAnchor="middle" dominantBaseline="middle">{n.label}</text>
              <text className="role" x={n.x} y={n.y + 9} textAnchor="middle" dominantBaseline="middle">{n.role}</text>
            </g>
          );
        })}

        {/* Team supervisors */}
        {TEAMS.map(n => {
          const isActive = active.has(n.id);
          return (
            <g key={n.id} className={`graph-node ${isActive ? (signal ? "signal" : "active") : ""}`}>
              <circle className="bg" cx={n.x} cy={n.y} r={28}/>
              {isActive && (
                <circle cx={n.x} cy={n.y} r={30} fill="none"
                  stroke={signal ? "var(--signal)" : "var(--accent)"} strokeWidth="1" opacity="0.6">
                  <animate attributeName="r" from="28" to="56" dur="1.6s" repeatCount="indefinite"/>
                  <animate attributeName="opacity" from="0.9" to="0" dur="1.6s" repeatCount="indefinite"/>
                </circle>
              )}
              <text className="label" x={n.x} y={n.y - 2} textAnchor="middle" dominantBaseline="middle" fontSize="10">{n.label}</text>
              <text className="role" x={n.x} y={n.y + 10} textAnchor="middle" dominantBaseline="middle">{n.role}</text>
            </g>
          );
        })}

        {/* Head (center) */}
        <g className={`graph-node ${active.has("head") ? (signal ? "signal" : "active") : ""}`}>
          <circle cx={CX} cy={CY} r={60} fill="url(#nodeGlow)"/>
          <circle className="bg" cx={CX} cy={CY} r={42}/>
          <circle cx={CX} cy={CY} r={32} fill="none" stroke="var(--line-2)" strokeDasharray="2 3"/>
          {active.has("head") && (
            <circle cx={CX} cy={CY} r={44} fill="none"
              stroke={signal ? "var(--signal)" : "var(--accent)"} strokeWidth="1.2" opacity="0.6">
              <animate attributeName="r" from="42" to="72" dur="2s" repeatCount="indefinite"/>
              <animate attributeName="opacity" from="0.9" to="0" dur="2s" repeatCount="indefinite"/>
            </circle>
          )}
          <text className="label" x={CX} y={CY - 4} textAnchor="middle" dominantBaseline="middle" fontSize="11">HEAD</text>
          <text className="role" x={CX} y={CY + 9} textAnchor="middle" dominantBaseline="middle" fontSize="8">supervisor</text>
          <text className="role" x={CX} y={CY + 20} textAnchor="middle" dominantBaseline="middle" fontSize="7" fill="var(--accent)">ORCH·01</text>
        </g>

        {/* Particles flowing along active edges */}
        {particles.map(p => {
          const { from, to, id } = p;
          return (
            <circle key={id} className={`particle ${signal ? "signal" : ""}`} r={3}>
              <animateMotion dur="1.0s" repeatCount="indefinite"
                path={`M${from.x},${from.y} L${to.x},${to.y}`}/>
              <animate attributeName="opacity" values="0;1;1;0" dur="1.0s" repeatCount="indefinite"/>
            </circle>
          );
        })}
      </svg>
    );
  }

  window.HeroGraph = HeroGraph;
  return HeroGraph;
})();
