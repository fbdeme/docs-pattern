// docs-hub 관계 그래프: 처음엔 지금 진행 중인 것만(show=base). 점을 누르면 그 아래(parent)를 펼치고 접는다, 두 번 누르면 그 page 로 간다.
(function () {
  const el = document.getElementById("hub-graph");
  if (!el || !window.vis) return;
  const dark = document.body.getAttribute("data-md-color-scheme") === "slate";
  const C = {   // 채도를 낮춘 종류색, 강조는 project 하나
    org: dark ? "#e6e6e6" : "#222", project: dark ? "#8fa8ff" : "#3f51b5", state: "#5b8def", issues: "#d9a441", rules: "#4fa37a", doc: "#9a7bd1",
    memo: dark ? "#7f9aa8" : "#8aa1ad", area: dark ? "#c8ccd4" : "#5f6670", skill: dark ? "#9aa3b2" : "#6b7685", store: dark ? "#e08a6b" : "#c0583a",
  };
  const NAME = { org: "조직", project: "프로젝트", state: "단계", issues: "이슈", rules: "Short Term Memory", doc: "Document",
                 memo: "Long Term Memory 메모", area: "분야(area)", skill: "스킬", store: "데이터 저장소" };
  const fg = getComputedStyle(document.body).getPropertyValue("--md-default-fg-color") || (dark ? "#ddd" : "#222");
  fetch(el.dataset.src).then(r => r.json()).then(g => {
    const deg = {};
    g.edges.forEach(e => { deg[e.from] = (deg[e.from] || 0) + 1; deg[e.to] = (deg[e.to] || 0) + 1; });
    const nodes = new vis.DataSet(g.nodes.map(n => ({
      id: n.id, kind: n.group, url: n.url, bad: n.bad, title: n.title || n.label,   // group 이라 부르면 vis 가 자기 색으로 덮는다
      label: n.label, show: n.show, parent: n.parent, hidden: n.show !== "base",
      value: (deg[n.id] || 0) + (n.group === "org" ? 20 : n.group === "project" ? 12 : n.group === "area" ? 4 : 0) + (n.must ? 6 : 0),
      color: { background: C[n.group], border: C[n.group],
               highlight: { background: C[n.group], border: fg }, hover: { background: C[n.group], border: fg } },
      borderWidth: 1, shape: "dot",
    })));
    const show = {}; g.nodes.forEach(n => (show[n.id] = n.show));
    const edges = new vis.DataSet(g.edges.map((e, i) => ({
      id: i, from: e.from, to: e.to, width: e.kind === "link" ? 1 : 0.5,
      length: show[e.from] !== "base" || show[e.to] !== "base" ? 130 : undefined,   // 펼친 점은 멀리 둘러서 이름이 겹치지 않게
      color: { color: dark ? "rgba(255,255,255,.14)" : "rgba(0,0,0,.12)", highlight: fg, hover: fg },
    })));
    const net = new vis.Network(el, { nodes, edges }, {
      nodes: { font: { color: fg.trim(), face: "inherit", size: 15 }, scaling: { min: 4, max: 22, label: { enabled: false } } },
      edges: { smooth: false },
      physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -30, springLength: 40, centralGravity: 0.08, damping: 0.6 }, stabilization: { iterations: 250 } },   // 점 30여 개 기준: 촘촘히 모아 이름이 읽히게
      interaction: { hover: true, tooltipDelay: 120 },
    });
    net.once("stabilizationIterationsDone", () => net.fit({ animation: false }));   // 자리 잡은 뒤 전체가 보이게
    window.hubGraph = net;   // 화면 시험(Playwright)이 점 자리를 읽는다
    // 마우스를 올린 점의 이웃만 밝게 (나머지는 흐리게)
    const base = {}; nodes.forEach(n => (base[n.id] = n.color.background));
    net.on("hoverNode", p => {
      const keep = new Set([p.node, ...net.getConnectedNodes(p.node)]);
      nodes.update(nodes.map(n => ({ id: n.id, opacity: keep.has(n.id) ? 1 : 0.15 })));
    });
    net.on("blurNode", () => nodes.update(nodes.map(n => ({ id: n.id, opacity: 1 }))));
    // 펼치기: 부모를 누르면 그 아래 점(show=child, '모두 보기'면 all 도)을 켜고 끈다. 아래가 없는 점은 바로 page 로
    const kids = {}; g.nodes.forEach(n => n.parent && (kids[n.parent] = kids[n.parent] || []).push(n.id));
    const open = new Set(), off = new Set(); let all = false, badOn = false;
    const vis_ = n => !off.has(n.kind) && (all || badOn && n.bad || n.show === "base" || (n.show === "child" && open.has(n.parent)));
    const named = n => n.show === "base" || open.has(n.parent);   // 이름은 기본 점과 펼친 점만, 나머지는 툴팁
    const refresh = () => nodes.update(nodes.map(n => ({ id: n.id, hidden: !vis_(n), font: { size: n.show === "base" ? 15 : named(n) ? 12 : 0 } })));
    const go = id => { const n = nodes.get(id); if (n && n.url) window.location.href = n.url; };
    net.on("click", p => { if (!p.nodes.length) return; const id = p.nodes[0];
      if (!kids[id]) return go(id);
      const opening = !open.has(id); opening ? open.add(id) : open.delete(id); refresh();
      // 펼친 묶음으로 확대해서 이름이 읽히게, 접으면 전체로
      setTimeout(() => net.fit({ nodes: opening ? [id, ...kids[id].filter(k => !nodes.get(k).hidden)] : undefined, animation: { duration: 400 } }), 600); });
    net.on("doubleClick", p => p.nodes.length && go(p.nodes[0]));
    // 범례 = 종류별 켜고 끄기
    const lg = document.getElementById("hub-legend");
    const count = {}; g.nodes.forEach(n => (count[n.group] = (count[n.group] || 0) + 1));
    const sAll = document.createElement("span"); sAll.className = "all"; sAll.textContent = `모두 보기 (${g.nodes.length})`;
    sAll.onclick = () => { all = !all; sAll.classList.toggle("on", all); refresh(); net.fit({ animation: false }); };
    lg.appendChild(sAll);
    Object.keys(NAME).filter(k => count[k]).forEach(k => {
      const s = document.createElement("span");
      s.innerHTML = `<i style="background:${C[k]}"></i>${NAME[k]} ${count[k]}`;
      s.onclick = () => { off.has(k) ? off.delete(k) : off.add(k); s.classList.toggle("off"); refresh(); };
      lg.appendChild(s);
    });
    // 문제 = 평소엔 조용히, 누르면 문제 점만 빨간 테두리로 밝히고 나머지는 흐리게
    const bad = g.nodes.filter(n => n.bad);
    if (bad.length) {
      const s = document.createElement("span"); s.className = "bad"; s.innerHTML = `<i></i>문제 ${bad.length} 보기 (검사 실패·양식 경고·상한 초과)`;
      s.onclick = () => { badOn = !badOn; const on = badOn; s.classList.toggle("on", on); refresh();
        nodes.update(g.nodes.map(n => ({ id: n.id, opacity: on && !n.bad ? 0.12 : 1,
          borderWidth: on && n.bad ? 3 : 1, color: { border: on && n.bad ? "#d84a4a" : C[n.group] } }))); };
      lg.appendChild(s);
    }
  });
})();
