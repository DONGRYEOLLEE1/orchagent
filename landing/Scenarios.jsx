/* Orchestration scenarios — steps drive both hero graph and demo console */

const Scenarios = {
  research: {
    id: "research",
    label: "RESEARCH",
    prompt: "Summarize the 2026 state of agent orchestration frameworks with sources",
    steps: [
      { t: 120,  ev: "ROUTE",  node: "head",    msg: "Head received request · classifying intent", nodes: ["head"], edges: [] },
      { t: 260,  ev: "REASON", node: "head",    msg: "Intent: multi-source research · delegating RESEARCH team", nodes: ["head"], edges: [["head","research"]] },
      { t: 380,  ev: "ROUTE",  node: "research",msg: "Research supervisor online · tool plan: tavily → scraper", nodes: ["research"], edges: [["head","research"]] },
      { t: 520,  ev: "TOOL",   node: "tavily",  msg: "tavily_search(q='agent orchestration frameworks 2026', k=8)", nodes: ["research","tavily"], edges: [["research","tavily"]] },
      { t: 720,  ev: "TEXT",   node: "tavily",  msg: "→ 8 hits · langgraph, autogen, crew, orchagent, mastra, ...", nodes: ["research","tavily"], edges: [["research","tavily"]] },
      { t: 900,  ev: "TOOL",   node: "scraper", msg: "web_scraper(urls=[3 docs]) · extracting structured md", nodes: ["research","scraper"], edges: [["research","scraper"]] },
      { t: 1080, ev: "REASON", node: "rval",    msg: "Validator · citation coverage 100% · context length ok", nodes: ["research","rval"], edges: [["research","rval"]], signal: true },
      { t: 1240, ev: "CKPT",   node: "research",msg: "Checkpoint ckpt_a5f · team FINISH → handing back", nodes: ["research","head"], edges: [["research","head"]] },
      { t: 1400, ev: "TEXT",   node: "head",    msg: "Synthesizing final answer · 4 frameworks compared", nodes: ["head"], edges: [] },
    ],
    answer: "Compared four frameworks across orchestration model, HITL primitives, and observability. LangGraph remains the reference — hierarchical supervisors are now table-stakes. Full citations attached below.",
    agent: "research",
  },
  vision: {
    id: "vision",
    label: "VISION",
    prompt: "Describe this satellite image and surface any anomalies",
    steps: [
      { t: 120,  ev: "ROUTE",  node: "head",    msg: "Multimodal input detected · 1 image, 1024×1024", nodes: ["head"], edges: [] },
      { t: 260,  ev: "REASON", node: "head",    msg: "Routing to VISION team · model-native vlm required", nodes: ["head"], edges: [["head","vision"]] },
      { t: 380,  ev: "ROUTE",  node: "vision",  msg: "Vision supervisor · pipeline: meta → analyst → validator", nodes: ["vision"], edges: [["head","vision"]] },
      { t: 500,  ev: "TOOL",   node: "vtools",  msg: "image_metadata() · 1024×1024 png · no exif", nodes: ["vision","vtools"], edges: [["vision","vtools"]] },
      { t: 660,  ev: "TOOL",   node: "vtools",  msg: "image_resize(target=768, mode='fit') · ok", nodes: ["vision","vtools"], edges: [["vision","vtools"]] },
      { t: 820,  ev: "REASON", node: "vana",    msg: "Analyst · coastal terrain · vessel anomaly cluster NE quadrant", nodes: ["vision","vana"], edges: [["vision","vana"]] },
      { t: 1000, ev: "TOOL",   node: "vval",    msg: "validator · confidence 0.84 < 0.9 · requesting second pass", nodes: ["vision","vval"], edges: [["vision","vval"]], signal: true },
      { t: 1160, ev: "ROUTE",  node: "vision",  msg: "Self-correction loop · re-running analyst with feedback", nodes: ["vision","vana"], edges: [["vision","vana"]] },
      { t: 1340, ev: "CKPT",   node: "vision",  msg: "ckpt_b12 · validated · FINISH → head", nodes: ["vision","head"], edges: [["vision","head"]] },
      { t: 1500, ev: "TEXT",   node: "head",    msg: "Final synthesis with confidence bounds", nodes: ["head"], edges: [] },
    ],
    answer: "Coastal terrain image, 1024×1024. Detected vessel anomaly cluster in NE quadrant, validated on second pass with 0.92 confidence. Full structured output + bounding boxes delivered.",
    agent: "vision",
  },
  writing: {
    id: "writing",
    label: "WRITING",
    prompt: "Draft a 400-word product brief from the research notes above",
    steps: [
      { t: 120,  ev: "ROUTE",  node: "head",    msg: "Resuming thread · context carries research team output", nodes: ["head"], edges: [] },
      { t: 260,  ev: "REASON", node: "head",    msg: "Target: 400w brief · delegating WRITING team", nodes: ["head"], edges: [["head","writing"]] },
      { t: 400,  ev: "ROUTE",  node: "writing", msg: "Writing supervisor · order: noter → writer → chart", nodes: ["writing"], edges: [["head","writing"]] },
      { t: 560,  ev: "TOOL",   node: "noter",   msg: "note_taker() · extracting 11 bullet points from context", nodes: ["writing","noter"], edges: [["writing","noter"]] },
      { t: 740,  ev: "TOOL",   node: "writer",  msg: "doc_writer(style='brief', len=400) · drafting...", nodes: ["writing","writer"], edges: [["writing","writer"]] },
      { t: 960,  ev: "HITL",   node: "head",    msg: "Pausing · awaiting tone approval (formal vs punchy)", nodes: ["writing","writer"], edges: [["writing","writer"]], signal: true, isHitl: true },
      { t: 1200, ev: "REASON", node: "writer",  msg: "Approved · continuing with formal tone", nodes: ["writing","writer"], edges: [["writing","writer"]] },
      { t: 1340, ev: "TOOL",   node: "chart",   msg: "chart_generator(data=benchmark) · rendering svg", nodes: ["writing","chart"], edges: [["writing","chart"]] },
      { t: 1500, ev: "CKPT",   node: "writing", msg: "ckpt_c03 · artifacts attached · FINISH → head", nodes: ["writing","head"], edges: [["writing","head"]] },
    ],
    answer: "Draft brief complete — 397 words, formal tone, chart attached. Artifacts: brief.md, benchmark.svg. Ready for review.",
    agent: "writing",
  },
};

window.Scenarios = Scenarios;
