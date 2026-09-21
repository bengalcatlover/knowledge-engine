"""知識グラフ成長リプレイサーバー — 0→100ノードの早回し再生"""
import http.server
import json
import sys
import webbrowser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 8766

HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>あきらぐ — Growth Replay</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #0a0a1a; color: #e0e0e0; overflow: hidden; }
#graph { width: 100vw; height: 100vh; }

#controls {
  position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
  background: rgba(10,10,26,0.95); border: 1px solid #444; border-radius: 12px;
  padding: 14px 24px; z-index: 20; display: flex; align-items: center; gap: 16px;
}
#controls button {
  background: #2ecc71; color: #000; border: none; padding: 8px 20px;
  border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold;
  transition: background 0.2s;
}
#controls button:hover { background: #27ae60; }
#controls button.pause { background: #e74c3c; }
#controls button.pause:hover { background: #c0392b; }
#speed-label { font-size: 13px; color: #aaa; }
#speed-slider { width: 120px; }

#counter {
  position: fixed; top: 16px; right: 16px; background: rgba(10,10,26,0.95);
  border: 1px solid #444; border-radius: 12px; padding: 16px 24px; z-index: 20;
  text-align: right;
}
#counter .big { font-size: 48px; font-weight: bold; color: #3498db; line-height: 1; }
#counter .label { font-size: 13px; color: #888; }
#counter .sub { font-size: 14px; color: #aaa; margin-top: 6px; }
#counter .sub .val { color: #2ecc71; font-weight: bold; }

#legend {
  position: fixed; bottom: 16px; left: 16px; background: rgba(10,10,26,0.92);
  border: 1px solid #333; border-radius: 8px; padding: 12px 16px; z-index: 10;
  font-size: 12px;
}
.legend-item { display: flex; align-items: center; margin: 3px 0; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }

#new-node {
  position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
  background: rgba(46,204,113,0.15); border: 1px solid #2ecc71;
  border-radius: 8px; padding: 10px 24px; z-index: 20;
  font-size: 15px; color: #2ecc71; opacity: 0; transition: opacity 0.3s;
  pointer-events: none; text-align: center;
}

#timeline {
  position: fixed; bottom: 60px; left: 50%; transform: translateX(-50%);
  width: 60%; z-index: 20;
}
#timeline input { width: 100%; }
#timeline-label {
  text-align: center; font-size: 11px; color: #666; margin-top: 2px;
}

#progress-bar {
  position: fixed; top: 0; left: 0; height: 3px; background: #3498db;
  z-index: 30; transition: width 0.3s;
}
</style>
</head>
<body>
<div id="progress-bar" style="width:0%"></div>

<div id="controls">
  <button id="play-btn" onclick="togglePlay()">▶ START</button>
  <span id="speed-label">Speed:</span>
  <input id="speed-slider" type="range" min="1" max="20" value="5"
    oninput="updateSpeed(this.value)">
  <span id="speed-val" style="color:#3498db;font-size:13px;min-width:30px">5x</span>
</div>

<div id="counter">
  <div class="big" id="node-count">0</div>
  <div class="label">nodes</div>
  <div class="sub">Edges: <span class="val" id="edge-count">0</span></div>
  <div class="sub">Claims: <span class="val" id="claim-count">-</span></div>
  <div class="sub">Domains: <span class="val" id="domain-count">0</span></div>
</div>

<div id="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>Foundation</div>
  <div class="legend-item"><div class="legend-dot" style="background:#3498db"></div>Science</div>
  <div class="legend-item"><div class="legend-dot" style="background:#2ecc71"></div>Universe</div>
  <div class="legend-item"><div class="legend-dot" style="background:#f39c12"></div>Object</div>
  <div class="legend-item"><div class="legend-dot" style="background:#9b59b6"></div>Practice</div>
</div>

<div id="new-node"></div>

<div id="timeline">
  <input type="range" id="timeline-slider" min="0" max="100" value="0"
    oninput="seekTo(parseInt(this.value))">
  <div id="timeline-label"></div>
</div>

<div id="graph"></div>

<script>
let replayData = null;
let network = null;
let nodesDS = null;
let edgesDS = null;
let currentStep = 0;
let playing = false;
let timer = null;
let speed = 5;  // nodes per second
let visibleNodeIds = new Set();

const layerColors = {
  foundation: '#e74c3c', science: '#3498db',
  universe: '#2ecc71', object: '#f39c12', practice: '#9b59b6'
};
const edgeColors = {
  COMPLEMENTS: '#3498db', HAS_SCOPED_INSTANCE: '#2ecc71',
  DERIVES_FROM: '#e74c3c', ABOUT: '#9b59b6',
  ABSTRACTS_FROM: '#f39c12', IS_A: '#1abc9c',
};

function makeVisNode(n, flash) {
  const color = layerColors[n.layer] || '#95a5a6';
  let label = n.title || n.id;
  if (label.length > 40) label = label.substring(0, 37) + '...';
  return {
    id: n.id, label: label, group: n.layer,
    color: {
      background: flash ? '#fff' : color, border: color,
      highlight: { background: '#fff', border: color },
      hover: { background: color, border: '#fff' },
    },
    size: flash ? 22 : (n.layer === 'foundation' ? 16 : 11),
    font: { color: '#ccc', face: 'Segoe UI', size: 10 },
    shadow: { enabled: true, color: color, size: flash ? 15 : 6, x: 0, y: 0 },
    borderWidth: 2,
  };
}

function initNetwork() {
  nodesDS = new vis.DataSet();
  edgesDS = new vis.DataSet();
  const container = document.getElementById('graph');
  network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -60, centralGravity: 0.008,
        springLength: 140, springConstant: 0.03, damping: 0.5, avoidOverlap: 0.5,
      },
      stabilization: false,
    },
    nodes: { shape: 'dot' },
    edges: { smooth: { type: 'continuous' }, font: { size: 0 } },
    interaction: { hover: true, tooltipDelay: 100 },
    layout: { improvedLayout: false },
  });
}

function addStep(idx) {
  if (idx >= replayData.nodes.length) {
    stopPlay();
    document.getElementById('play-btn').textContent = '✓ DONE';
    return;
  }
  const n = replayData.nodes[idx];
  visibleNodeIds.add(n.id);

  // Add node with flash
  nodesDS.add(makeVisNode(n, true));
  setTimeout(() => {
    try { nodesDS.update(makeVisNode(n, false)); } catch(e) {}
  }, 800);

  // Add any edges whose both ends are now visible
  const newEdges = replayData.edges.filter(e =>
    visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)
    && !edgesDS.get(e.from + '>' + e.to)
  );
  newEdges.forEach(e => {
    edgesDS.add({
      id: e.from + '>' + e.to,
      from: e.from, to: e.to,
      color: { color: edgeColors[e.type] || '#bdc3c7', opacity: 0.6 },
      arrows: 'to', width: 1,
    });
  });

  // Update counters
  currentStep = idx + 1;
  document.getElementById('node-count').textContent = currentStep;
  document.getElementById('edge-count').textContent = edgesDS.length;
  document.getElementById('progress-bar').style.width =
    (currentStep / replayData.nodes.length * 100) + '%';
  document.getElementById('timeline-slider').value = currentStep;

  // Domains
  const domains = new Set();
  for (let i = 0; i < currentStep; i++) domains.add(replayData.nodes[i].domain || replayData.nodes[i].layer);
  document.getElementById('domain-count').textContent = domains.size;

  // Flash notification
  const notif = document.getElementById('new-node');
  notif.textContent = '+ ' + n.id + '  ' + (n.title || '');
  notif.style.opacity = '1';
  setTimeout(() => { notif.style.opacity = '0'; }, 600);

  // Timeline label
  if (n.ts) {
    const d = new Date(n.ts);
    document.getElementById('timeline-label').textContent =
      d.toLocaleDateString('ja-JP') + ' ' + d.toLocaleTimeString('ja-JP', {hour:'2-digit',minute:'2-digit'});
  }
}

function togglePlay() {
  if (playing) { stopPlay(); }
  else { startPlay(); }
}

function startPlay() {
  if (currentStep >= replayData.nodes.length) {
    // Reset
    currentStep = 0;
    visibleNodeIds.clear();
    nodesDS.clear();
    edgesDS.clear();
  }
  playing = true;
  document.getElementById('play-btn').textContent = '⏸ PAUSE';
  document.getElementById('play-btn').classList.add('pause');
  tick();
}

function stopPlay() {
  playing = false;
  if (timer) { clearTimeout(timer); timer = null; }
  document.getElementById('play-btn').textContent = '▶ PLAY';
  document.getElementById('play-btn').classList.remove('pause');
}

function tick() {
  if (!playing) return;
  addStep(currentStep);
  if (currentStep < replayData.nodes.length) {
    timer = setTimeout(tick, 1000 / speed);
  }
}

function updateSpeed(val) {
  speed = parseInt(val);
  document.getElementById('speed-val').textContent = speed + 'x';
}

function seekTo(idx) {
  stopPlay();
  // Rebuild up to idx
  visibleNodeIds.clear();
  nodesDS.clear();
  edgesDS.clear();
  for (let i = 0; i < idx; i++) {
    const n = replayData.nodes[i];
    visibleNodeIds.add(n.id);
    nodesDS.add(makeVisNode(n, false));
  }
  // Add all valid edges
  replayData.edges.forEach(e => {
    if (visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)) {
      edgesDS.add({
        id: e.from + '>' + e.to,
        from: e.from, to: e.to,
        color: { color: edgeColors[e.type] || '#bdc3c7', opacity: 0.6 },
        arrows: 'to', width: 1,
      });
    }
  });
  currentStep = idx;
  document.getElementById('node-count').textContent = currentStep;
  document.getElementById('edge-count').textContent = edgesDS.length;
  document.getElementById('progress-bar').style.width =
    (currentStep / replayData.nodes.length * 100) + '%';
  document.getElementById('timeline-slider').value = currentStep;
}

// Load data and init
fetch('/api/replay')
  .then(r => r.json())
  .then(data => {
    replayData = data;
    document.getElementById('claim-count').textContent = data.meta.claims;
    document.getElementById('timeline-slider').max = data.nodes.length;
    initNetwork();
  });
</script>
</body>
</html>"""


def build_replay_json():
    from mvp_store import init_db
    db = init_db()

    # Nodes ordered by creation time
    rows = db.execute("""
        SELECT n.id, n.layer, n.status, json_extract(n.data, '$.title'), e.occurred_at
        FROM node n
        JOIN event e ON e.entity_ref = n.id AND e.event_type = 'node_created'
        WHERE n.status != 'superseded'
        ORDER BY e.occurred_at
    """).fetchall()

    node_ids = set(r[0] for r in rows)

    edges_raw = db.execute("SELECT from_node, to_node, type FROM edge").fetchall()
    edges_raw = [(f, t, ty) for f, t, ty in edges_raw if f in node_ids and t in node_ids]

    claims = db.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    evidence = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    nodes = []
    for nid, layer, status, title, ts in rows:
        label = title or nid
        nodes.append({"id": nid, "layer": layer, "title": label, "ts": ts})

    edges = [{"from": f, "to": t, "type": ty} for f, t, ty in edges_raw]

    return json.dumps({
        "nodes": nodes, "edges": edges,
        "meta": {"claims": claims, "evidence": evidence},
    }, ensure_ascii=False)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/replay":
            data = build_replay_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Replay server: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
