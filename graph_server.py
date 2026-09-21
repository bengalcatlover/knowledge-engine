"""知識グラフ可視化サーバー — DBから直接JSONを生成して配信"""
import http.server
import json
import sys
import webbrowser
from io import BytesIO

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 8765
HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>あきらぐ — Knowledge Engine Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #0a0a1a; color: #e0e0e0; }
#graph { width: 100vw; height: 100vh; }
#legend {
  position: fixed; top: 16px; left: 16px; background: rgba(10,10,26,0.92);
  border: 1px solid #333; border-radius: 8px; padding: 16px; z-index: 10;
  font-size: 13px; min-width: 200px;
}
#legend h2 { font-size: 16px; margin-bottom: 10px; color: #fff; }
.legend-item { display: flex; align-items: center; margin: 5px 0; }
.legend-dot { width: 14px; height: 14px; border-radius: 50%; margin-right: 8px; flex-shrink: 0; }
#stats {
  position: fixed; top: 16px; right: 16px; background: rgba(10,10,26,0.92);
  border: 1px solid #333; border-radius: 8px; padding: 16px; z-index: 10;
  font-size: 13px;
}
#stats h2 { font-size: 16px; margin-bottom: 10px; color: #fff; }
#stats .stat { margin: 4px 0; }
#stats .val { color: #3498db; font-weight: bold; }
#info {
  position: fixed; bottom: 16px; left: 16px; right: 16px;
  background: rgba(10,10,26,0.95); border: 1px solid #333;
  border-radius: 8px; padding: 12px 16px; z-index: 10;
  font-size: 12px; display: none; max-height: 150px; overflow-y: auto;
}
#info h3 { color: #f39c12; margin-bottom: 4px; }
#edge-legend {
  position: fixed; bottom: 16px; right: 16px; background: rgba(10,10,26,0.92);
  border: 1px solid #333; border-radius: 8px; padding: 12px; z-index: 10;
  font-size: 11px;
}
#edge-legend h3 { font-size: 13px; margin-bottom: 6px; color: #fff; }
.edge-item { display: flex; align-items: center; margin: 3px 0; }
.edge-line { width: 20px; height: 3px; margin-right: 6px; border-radius: 2px; }
</style>
</head>
<body>
<div id="legend">
  <h2>あきらぐ Knowledge Graph</h2>
  <div class="legend-item"><div class="legend-dot" style="background:#e74c3c"></div>基礎科学 (Foundation)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#3498db"></div>科学 (Science)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#2ecc71"></div>世界モデル (Universe)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#f39c12"></div>実行 (Object)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#9b59b6"></div>実践 (Practice)</div>
</div>
<div id="stats">
  <h2>Stats</h2>
  <div class="stat">Nodes: <span class="val" id="s-nodes">-</span></div>
  <div class="stat">Edges: <span class="val" id="s-edges">-</span></div>
  <div class="stat">Edge/Node: <span class="val" id="s-ratio">-</span></div>
  <div class="stat">Claims: <span class="val" id="s-claims">-</span></div>
  <div class="stat">Evidence: <span class="val" id="s-evidence">-</span></div>
  <div style="margin-top:10px;border-top:1px solid #333;padding-top:8px">
    <button id="live-btn" onclick="toggleLive()"
      style="background:#2ecc71;color:#000;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px">
      LIVE
    </button>
    <span id="live-status" style="margin-left:6px;font-size:11px;color:#2ecc71">3s polling</span>
  </div>
  <div id="activity" style="margin-top:6px;font-size:11px;color:#f39c12;max-height:60px;overflow-y:auto"></div>
</div>
<div id="edge-legend">
  <h3>Edge Types</h3>
  <div class="edge-item"><div class="edge-line" style="background:#3498db"></div>COMPLEMENTS</div>
  <div class="edge-item"><div class="edge-line" style="background:#2ecc71"></div>HAS_SCOPED_INSTANCE</div>
  <div class="edge-item"><div class="edge-line" style="background:#e74c3c"></div>DERIVES_FROM</div>
  <div class="edge-item"><div class="edge-line" style="background:#9b59b6"></div>ABOUT</div>
  <div class="edge-item"><div class="edge-line" style="background:#f39c12"></div>ABSTRACTS_FROM</div>
  <div class="edge-item"><div class="edge-line" style="background:#1abc9c"></div>IS_A</div>
  <div class="edge-item"><div class="edge-line" style="background:#bdc3c7"></div>Other</div>
</div>
<div id="info"></div>
<div id="graph"></div>
<script>
let network = null;
let nodesDS = null;
let edgesDS = null;
let liveMode = true;
let pollTimer = null;
let lastNodeCount = 0;
let lastEdgeCount = 0;
let currentData = null;

function styleNode(n) {
  n.borderWidth = 2;
  n.borderWidthSelected = 3;
  n.color = {
    background: n.color, border: n.color,
    highlight: { background: '#fff', border: n.color },
    hover: { background: n.color, border: '#fff' },
  };
  n.shadow = { enabled: true, color: n.color.background || n.color, size: 6, x: 0, y: 0 };
  return n;
}

function logActivity(msg) {
  const el = document.getElementById('activity');
  const t = new Date().toLocaleTimeString();
  el.innerHTML = '<div>' + t + ' ' + msg + '</div>' + el.innerHTML;
  if (el.children.length > 10) el.removeChild(el.lastChild);
}

function updateStats(data) {
  document.getElementById('s-nodes').textContent = data.nodes.length;
  document.getElementById('s-edges').textContent = data.edges.length;
  document.getElementById('s-ratio').textContent = (data.edges.length / Math.max(data.nodes.length,1)).toFixed(2);
  document.getElementById('s-claims').textContent = data.meta.claims;
  document.getElementById('s-evidence').textContent = data.meta.evidence;
}

function initGraph(data) {
  currentData = data;
  data.nodes.forEach(styleNode);
  updateStats(data);
  lastNodeCount = data.nodes.length;
  lastEdgeCount = data.edges.length;

  nodesDS = new vis.DataSet(data.nodes);
  edgesDS = new vis.DataSet(data.edges);

  const container = document.getElementById('graph');
  network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -50, centralGravity: 0.008,
        springLength: 130, springConstant: 0.04, damping: 0.4, avoidOverlap: 0.5,
      },
      stabilization: { iterations: 300 },
    },
    nodes: { shape: 'dot', font: { color: '#ccc', face: 'Segoe UI', size: 10 } },
    edges: { smooth: { type: 'continuous' }, font: { size: 0 } },
    interaction: { hover: true, tooltipDelay: 100, keyboard: true },
    layout: { improvedLayout: true },
  });

  network.on('click', params => {
    const info = document.getElementById('info');
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node = currentData.nodes.find(n => n.id === nodeId);
      const connected = currentData.edges.filter(e => e.from === nodeId || e.to === nodeId);
      info.style.display = 'block';
      info.innerHTML = '<h3>' + node.id + ' — ' + node.label + '</h3>'
        + '<div>Layer: ' + node.group + ' | Connections: ' + connected.length + '</div>'
        + '<div style="margin-top:4px;color:#aaa">'
        + connected.map(e => {
            const other = e.from === nodeId ? e.to : e.from;
            const on = currentData.nodes.find(n => n.id === other);
            return '&#8594; ' + e.title + ': ' + other + ' (' + (on ? on.label : '?') + ')';
          }).join('<br>')
        + '</div>';
    } else {
      info.style.display = 'none';
    }
  });

  logActivity('Graph loaded');
  if (liveMode) startPolling();
}

function refreshGraph(data) {
  currentData = data;
  data.nodes.forEach(styleNode);
  updateStats(data);

  // Detect changes
  const newNodeIds = new Set(data.nodes.map(n => n.id));
  const oldNodeIds = new Set(nodesDS.getIds());
  const addedNodes = data.nodes.filter(n => !oldNodeIds.has(n.id));
  const removedIds = [...oldNodeIds].filter(id => !newNodeIds.has(id));

  const newEdgeKeys = new Set(data.edges.map(e => e.from + '>' + e.to));
  const oldEdgeKeys = new Set(edgesDS.get().map(e => e.from + '>' + e.to));
  const addedEdges = data.edges.filter(e => !oldEdgeKeys.has(e.from + '>' + e.to));

  if (addedNodes.length === 0 && removedIds.length === 0 && addedEdges.length === 0
      && data.meta.claims === lastNodeCount) {
    // Check meta changes
    if (data.nodes.length !== lastNodeCount || data.edges.length !== lastEdgeCount) {
      // stats changed but graph topology same
    } else {
      return; // no change
    }
  }

  // Apply incremental updates (no layout reset)
  if (addedNodes.length > 0) {
    // Flash new nodes bright
    addedNodes.forEach(n => {
      n.size = (n.size || 11) + 6;
      setTimeout(() => { nodesDS.update({ id: n.id, size: n.size - 6 }); }, 2000);
    });
    nodesDS.add(addedNodes);
    logActivity('+' + addedNodes.length + ' nodes: ' + addedNodes.map(n => n.id).join(', '));
  }
  if (removedIds.length > 0) {
    nodesDS.remove(removedIds);
    logActivity('-' + removedIds.length + ' nodes');
  }
  if (addedEdges.length > 0) {
    edgesDS.add(addedEdges);
    logActivity('+' + addedEdges.length + ' edges');
  }

  lastNodeCount = data.nodes.length;
  lastEdgeCount = data.edges.length;
}

function poll() {
  fetch('/api/graph')
    .then(r => r.json())
    .then(data => {
      if (network) refreshGraph(data);
      else initGraph(data);
    })
    .catch(() => {});
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(poll, 3000);
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function toggleLive() {
  liveMode = !liveMode;
  const btn = document.getElementById('live-btn');
  const st = document.getElementById('live-status');
  if (liveMode) {
    btn.style.background = '#2ecc71';
    btn.textContent = 'LIVE';
    st.textContent = '3s polling';
    st.style.color = '#2ecc71';
    startPolling();
  } else {
    btn.style.background = '#e74c3c';
    btn.textContent = 'PAUSED';
    st.textContent = 'stopped';
    st.style.color = '#e74c3c';
    stopPolling();
  }
}

// Initial load
fetch('/api/graph').then(r => r.json()).then(initGraph);
</script>
</body>
</html>"""


def build_graph_json():
    from mvp_store import init_db
    db = init_db()

    nodes_raw = db.execute(
        "SELECT id, layer, status, json_extract(data, '$.title') FROM node "
        "WHERE status != 'superseded' ORDER BY id"
    ).fetchall()
    edges_raw = db.execute("SELECT from_node, to_node, type FROM edge").fetchall()
    claims = db.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    evidence = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]

    node_ids = set(n[0] for n in nodes_raw)
    edges_raw = [(f, t, ty) for f, t, ty in edges_raw if f in node_ids and t in node_ids]

    layer_colors = {
        "foundation": "#e74c3c", "science": "#3498db",
        "universe": "#2ecc71", "object": "#f39c12", "practice": "#9b59b6",
    }
    edge_colors = {
        "COMPLEMENTS": "#3498db", "HAS_SCOPED_INSTANCE": "#2ecc71",
        "DERIVES_FROM": "#e74c3c", "ABOUT": "#9b59b6",
        "ABSTRACTS_FROM": "#f39c12", "IS_A": "#1abc9c",
    }

    vis_nodes = []
    for nid, layer, status, title in nodes_raw:
        label = title or nid
        if len(label) > 45:
            label = label[:42] + "..."
        vis_nodes.append({
            "id": nid, "label": label, "group": layer,
            "color": layer_colors.get(layer, "#95a5a6"),
            "size": 16 if layer == "foundation" else 11,
            "title": f"{nid} | {title or nid}",
            "font": {"size": 10},
        })

    vis_edges = []
    for f, t, ty in edges_raw:
        vis_edges.append({
            "from": f, "to": t,
            "color": {"color": edge_colors.get(ty, "#bdc3c7"), "opacity": 0.6},
            "title": ty, "arrows": "to", "width": 1,
        })

    return json.dumps({
        "nodes": vis_nodes, "edges": vis_edges,
        "meta": {"claims": claims, "evidence": evidence},
    }, ensure_ascii=False)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/graph":
            data = build_graph_json().encode("utf-8")
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
        pass  # quiet


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Graph server: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
