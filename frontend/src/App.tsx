import { useState, useCallback, useEffect, useRef } from "react";
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  Handle,
} from "reactflow";
import "reactflow/dist/style.css";

// ─── Types (inline for single-file artifact) ──────────────────────────────────

type RepoStatus = "pending" | "processing" | "completed" | "failed";

interface Repository {
  id: string;
  owner: string;
  name: string;
  url: string;
  description?: string;
  language?: string;
  stars: number;
  forks: number;
  status: RepoStatus;
  default_branch: string;
}

interface GraphNodeData {
  id: string;
  path: string;
  file_type: string;
  fan_in: number;
  fan_out: number;
  is_entry_point: boolean;
  in_cycle: boolean;
  centrality_score: number;
}

interface DependencyEdge {
  source: string;
  target: string;
}

interface DependencyGraph {
  nodes: GraphNodeData[];
  edges: DependencyEdge[];
  node_count: number;
  edge_count: number;
}

interface ArchRisk {
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  description: string;
  affected_files: string[];
  recommendation: string;
}

interface ArchReport {
  health_score: number;
  health_label: string;
  risks: ArchRisk[];
  metrics: Record<string, number>;
  decomposition_suggestions: Array<{
    type: string;
    title: string;
    description: string;
    files: string[];
    confidence: string;
  }>;
}

interface ImpactResult {
  file_path: string;
  directly_affected: string[];
  transitively_affected: string[];
  impact_score: number;
  affected_count: number;
  impact_percentage: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  grounded_in?: string[];
}

type View = "home" | "graph" | "impact" | "report" | "chat";

// ─── API Client ───────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:8000/api/v1";

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ─── Design Tokens ────────────────────────────────────────────────────────────

const COLORS = {
  bg: "#0a0e1a",
  surface: "#111827",
  border: "#1e2a3d",
  borderBright: "#2d3f5c",
  accent: "#3b82f6",
  accentGlow: "#3b82f630",
  accentDim: "#1d4ed8",
  green: "#10b981",
  yellow: "#f59e0b",
  red: "#ef4444",
  orange: "#f97316",
  purple: "#8b5cf6",
  cyan: "#06b6d4",
  textPrimary: "#f0f4f8",
  textSecondary: "#8a9bb5",
  textDim: "#4a5568",
};

const SEVERITY_CONFIG = {
  critical: { color: COLORS.red, bg: "#ef444415", label: "CRITICAL" },
  high: { color: COLORS.orange, bg: "#f9731615", label: "HIGH" },
  medium: { color: COLORS.yellow, bg: "#f59e0b15", label: "MEDIUM" },
  low: { color: COLORS.cyan, bg: "#06b6d415", label: "LOW" },
};

// ─── Custom Graph Node Component ──────────────────────────────────────────────

function FileNode({ data }: { data: GraphNodeData & { selected?: boolean } }) {
  const fileName = data.path.split("/").pop() || data.path;
  const isHotspot = data.fan_in > 8;
  const color = data.in_cycle
    ? COLORS.red
    : isHotspot
    ? COLORS.orange
    : data.is_entry_point
    ? COLORS.green
    : data.file_type === "python"
    ? COLORS.cyan
    : data.file_type === "typescript"
    ? COLORS.accent
    : COLORS.purple;

  return (
    <div
      style={{
        background: `${color}18`,
        border: `1px solid ${color}50`,
        borderRadius: 8,
        padding: "6px 10px",
        minWidth: 120,
        maxWidth: 200,
        cursor: "pointer",
        transition: "all 0.15s",
        boxShadow: data.selected ? `0 0 12px ${color}60` : "none",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: color, border: "none", width: 6, height: 6 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 12 }}>
          {data.file_type === "python" ? "🐍" : data.file_type === "typescript" ? "🔷" : "📄"}
        </span>
        <span style={{ color: COLORS.textPrimary, fontSize: 11, fontWeight: 600, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {fileName}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
        <span style={{ fontSize: 9, color: COLORS.textSecondary }}>↙{data.fan_in}</span>
        <span style={{ fontSize: 9, color: COLORS.textSecondary }}>↗{data.fan_out}</span>
        {data.in_cycle && <span style={{ fontSize: 9, color: COLORS.red }}>⟳</span>}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: color, border: "none", width: 6, height: 6 }} />
    </div>
  );
}

const nodeTypes = { fileNode: FileNode };

// ─── Subcomponents ────────────────────────────────────────────────────────────

function MetricCard({ label, value, sub, color = COLORS.accent }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "16px 20px" }}>
      <div style={{ color: COLORS.textSecondary, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{label}</div>
      <div style={{ color, fontSize: 28, fontWeight: 700, fontFamily: "monospace", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ color: COLORS.textDim, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function HealthRing({ score, label }: { score: number; label: string }) {
  const r = 52;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 75 ? COLORS.green : score >= 50 ? COLORS.yellow : COLORS.red;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <svg width={128} height={128} viewBox="0 0 128 128">
        <circle cx={64} cy={64} r={r} fill="none" stroke={COLORS.border} strokeWidth={8} />
        <circle
          cx={64} cy={64} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 64 64)"
          style={{ transition: "stroke-dashoffset 1s ease", filter: `drop-shadow(0 0 6px ${color})` }}
        />
        <text x={64} y={60} textAnchor="middle" fill={color} fontSize={22} fontWeight={700} fontFamily="monospace">{score}</text>
        <text x={64} y={78} textAnchor="middle" fill={COLORS.textSecondary} fontSize={9}>/100</text>
      </svg>
      <span style={{ color, fontSize: 13, fontWeight: 600 }}>{label}</span>
    </div>
  );
}

function RiskBadge({ severity }: { severity: ArchRisk["severity"] }) {
  const cfg = SEVERITY_CONFIG[severity];
  return (
    <span style={{
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}40`,
      fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
      padding: "2px 7px", borderRadius: 4, fontFamily: "monospace",
    }}>{cfg.label}</span>
  );
}

function Spinner() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: 40 }}>
      <div style={{
        width: 36, height: 36, border: `3px solid ${COLORS.border}`,
        borderTopColor: COLORS.accent, borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }} />
      <span style={{ color: COLORS.textSecondary, fontSize: 13 }}>Analyzing repository…</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function NavButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{
      background: active ? COLORS.accentGlow : "transparent",
      color: active ? COLORS.accent : COLORS.textSecondary,
      border: "none", borderRadius: 6, padding: "7px 14px",
      fontSize: 13, fontWeight: active ? 600 : 400, cursor: "pointer",
      transition: "all 0.15s", display: "flex", alignItems: "center", gap: 6,
    }}>
      {children}
    </button>
  );
}

// ─── Views ────────────────────────────────────────────────────────────────────

function HomeView({ onAnalyze, repos, onSelectRepo, loading, error }: {
  onAnalyze: (url: string) => void;
  repos: Repository[];
  onSelectRepo: (repo: Repository) => void;
  loading: boolean;
  error?: string;
}) {
  const [url, setUrl] = useState("");

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "48px 24px" }}>
      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          background: COLORS.accentGlow, border: `1px solid ${COLORS.accent}30`,
          borderRadius: 20, padding: "4px 14px", marginBottom: 20,
        }}>
          <span style={{ color: COLORS.accent, fontSize: 11, fontWeight: 600, letterSpacing: "0.1em" }}>ARCHITECTURE INTELLIGENCE</span>
        </div>
        <h1 style={{
          color: COLORS.textPrimary, fontSize: 44, fontWeight: 800, lineHeight: 1.1,
          margin: "0 0 12px", letterSpacing: "-0.02em",
        }}>
          Understand your{" "}
          <span style={{ color: COLORS.accent }}>codebase</span>
        </h1>
        <p style={{ color: COLORS.textSecondary, fontSize: 16, maxWidth: 540, margin: "0 auto", lineHeight: 1.6 }}>
          Graph-powered dependency analysis. Find cycles, hotspots, and blast radius — then ask the AI architect to explain it.
        </p>
      </div>

      {/* Input */}
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24, marginBottom: 32 }}>
        <div style={{ color: COLORS.textSecondary, fontSize: 12, marginBottom: 10, letterSpacing: "0.05em" }}>
          GITHUB REPOSITORY URL
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && url && onAnalyze(url)}
            placeholder="https://github.com/owner/repository"
            style={{
              flex: 1, background: COLORS.bg, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, padding: "10px 14px", color: COLORS.textPrimary,
              fontSize: 14, fontFamily: "monospace", outline: "none",
              transition: "border-color 0.15s",
            }}
            onFocus={(e) => (e.target.style.borderColor = COLORS.accent)}
            onBlur={(e) => (e.target.style.borderColor = COLORS.border)}
          />
          <button
            onClick={() => url && onAnalyze(url)}
            disabled={!url || loading}
            style={{
              background: url && !loading ? COLORS.accent : COLORS.border,
              color: COLORS.textPrimary, border: "none", borderRadius: 8,
              padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: url && !loading ? "pointer" : "not-allowed",
              transition: "all 0.15s", whiteSpace: "nowrap",
            }}
          >
            {loading ? "Analyzing…" : "Analyze →"}
          </button>
        </div>
        {error && (
          <div style={{ color: COLORS.red, fontSize: 12, marginTop: 10, padding: "8px 12px", background: "#ef444415", borderRadius: 6 }}>
            {error}
          </div>
        )}
      </div>

      {/* Previous repos */}
      {repos.length > 0 && (
        <div>
          <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>
            PREVIOUSLY ANALYZED
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {repos.slice(0, 5).map((repo) => (
              <button
                key={repo.id}
                onClick={() => onSelectRepo(repo)}
                style={{
                  background: COLORS.surface, border: `1px solid ${COLORS.border}`,
                  borderRadius: 8, padding: "12px 16px", cursor: "pointer",
                  textAlign: "left", transition: "border-color 0.15s",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = COLORS.borderBright)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = COLORS.border)}
              >
                <div>
                  <span style={{ color: COLORS.textPrimary, fontSize: 14, fontWeight: 600, fontFamily: "monospace" }}>
                    {repo.owner}/{repo.name}
                  </span>
                  {repo.description && (
                    <p style={{ color: COLORS.textSecondary, fontSize: 12, margin: "2px 0 0" }}>
                      {repo.description.slice(0, 80)}
                    </p>
                  )}
                </div>
                <div style={{ display: "flex", gap: 12, color: COLORS.textDim, fontSize: 11 }}>
                  {repo.language && <span>{repo.language}</span>}
                  <span>★ {repo.stars.toLocaleString()}</span>
                  <StatusBadge status={repo.status} />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: RepoStatus }) {
  const cfg = {
    completed: { color: COLORS.green, label: "Ready" },
    processing: { color: COLORS.yellow, label: "Processing" },
    pending: { color: COLORS.textDim, label: "Pending" },
    failed: { color: COLORS.red, label: "Failed" },
  }[status];
  return <span style={{ color: cfg.color, fontWeight: 600 }}>{cfg.label}</span>;
}

function GraphView({ repoId }: { repoId: string }) {
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    setLoading(true);
    apiGet<DependencyGraph>(`/repositories/${repoId}/graph`)
      .then((g) => {
        setGraph(g);
        buildFlowGraph(g);
      })
      .finally(() => setLoading(false));
  }, [repoId]);

  const buildFlowGraph = (g: DependencyGraph) => {
    // Simple force-directed layout approximation
    const n = g.nodes.length;
    const cols = Math.ceil(Math.sqrt(n * 2));
    const spacing = 180;

    const flowNodes: Node[] = g.nodes.slice(0, 200).map((node, i) => ({
      id: node.id,
      type: "fileNode",
      position: {
        x: (i % cols) * spacing,
        y: Math.floor(i / cols) * 80,
      },
      data: node,
    }));

    const nodeSet = new Set(flowNodes.map((n) => n.id));
    const flowEdges: Edge[] = g.edges
      .filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target))
      .slice(0, 500)
      .map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#2d3f5c", width: 8, height: 8 },
        style: { stroke: "#2d3f5c", strokeWidth: 1 },
        animated: false,
      }));

    setNodes(flowNodes);
    setEdges(flowEdges);
  };

  if (loading) return <Spinner />;

  return (
    <div style={{ height: "calc(100vh - 100px)", display: "flex" }}>
      {/* Graph */}
      <div style={{ flex: 1, background: COLORS.bg }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedNode(node.data as GraphNodeData)}
          fitView
          fitViewOptions={{ padding: 0.1 }}
          minZoom={0.1}
          maxZoom={3}
        >
          <Background color="#1e2a3d" gap={20} size={1} />
          <Controls style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8 }} />
          <MiniMap
            style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}` }}
            nodeColor={(n) => n.data?.in_cycle ? COLORS.red : n.data?.is_entry_point ? COLORS.green : COLORS.accent}
          />
        </ReactFlow>
      </div>

      {/* Sidebar */}
      <div style={{
        width: 280, background: COLORS.surface, borderLeft: `1px solid ${COLORS.border}`,
        padding: 20, overflowY: "auto", display: "flex", flexDirection: "column", gap: 20,
      }}>
        <div>
          <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>GRAPH OVERVIEW</div>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1, background: COLORS.bg, borderRadius: 8, padding: "10px 12px", textAlign: "center" }}>
              <div style={{ color: COLORS.accent, fontSize: 22, fontWeight: 700, fontFamily: "monospace" }}>{graph?.node_count}</div>
              <div style={{ color: COLORS.textDim, fontSize: 10 }}>NODES</div>
            </div>
            <div style={{ flex: 1, background: COLORS.bg, borderRadius: 8, padding: "10px 12px", textAlign: "center" }}>
              <div style={{ color: COLORS.cyan, fontSize: 22, fontWeight: 700, fontFamily: "monospace" }}>{graph?.edge_count}</div>
              <div style={{ color: COLORS.textDim, fontSize: 10 }}>EDGES</div>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div>
          <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 10 }}>LEGEND</div>
          {[
            { color: COLORS.green, label: "Entry point" },
            { color: COLORS.red, label: "In cycle" },
            { color: COLORS.orange, label: "Hotspot (high fan-in)" },
            { color: COLORS.cyan, label: "Python module" },
            { color: COLORS.accent, label: "TypeScript module" },
          ].map((l) => (
            <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: l.color }} />
              <span style={{ color: COLORS.textSecondary, fontSize: 12 }}>{l.label}</span>
            </div>
          ))}
        </div>

        {/* Selected node */}
        {selectedNode && (
          <div style={{ background: COLORS.bg, borderRadius: 8, padding: 14, border: `1px solid ${COLORS.border}` }}>
            <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 8 }}>SELECTED FILE</div>
            <div style={{ color: COLORS.textPrimary, fontSize: 13, fontFamily: "monospace", wordBreak: "break-all", marginBottom: 10 }}>
              {selectedNode.path}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                ["Fan-in", selectedNode.fan_in, COLORS.cyan],
                ["Fan-out", selectedNode.fan_out, COLORS.purple],
                ["Centrality", selectedNode.centrality_score.toFixed(3), COLORS.accent],
                ["In cycle", selectedNode.in_cycle ? "Yes" : "No", selectedNode.in_cycle ? COLORS.red : COLORS.green],
              ].map(([l, v, c]) => (
                <div key={String(l)} style={{ background: COLORS.surface, borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ color: COLORS.textDim, fontSize: 9, marginBottom: 2 }}>{l}</div>
                  <div style={{ color: c as string, fontSize: 16, fontWeight: 700, fontFamily: "monospace" }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ImpactView({ repoId }: { repoId: string }) {
  const [filePath, setFilePath] = useState("");
  const [result, setResult] = useState<ImpactResult | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = async () => {
    if (!filePath) return;
    setLoading(true);
    try {
      const r = await apiPost<ImpactResult>(`/repositories/${repoId}/impact`, {
        repository_id: repoId,
        file_path: filePath,
        max_depth: 15,
      });
      setResult(r);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 800 }}>
      <h2 style={{ color: COLORS.textPrimary, fontSize: 22, fontWeight: 700, marginBottom: 6 }}>Impact Analysis</h2>
      <p style={{ color: COLORS.textSecondary, fontSize: 14, marginBottom: 28 }}>
        "What breaks if I change this file?" — DFS on the reversed dependency graph.
      </p>

      <div style={{ display: "flex", gap: 10, marginBottom: 28 }}>
        <input
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && analyze()}
          placeholder="e.g. src/auth/auth.py"
          style={{
            flex: 1, background: COLORS.surface, border: `1px solid ${COLORS.border}`,
            borderRadius: 8, padding: "10px 14px", color: COLORS.textPrimary,
            fontSize: 14, fontFamily: "monospace", outline: "none",
          }}
          onFocus={(e) => (e.target.style.borderColor = COLORS.accent)}
          onBlur={(e) => (e.target.style.borderColor = COLORS.border)}
        />
        <button
          onClick={analyze}
          disabled={!filePath || loading}
          style={{
            background: COLORS.accent, color: "#fff", border: "none",
            borderRadius: 8, padding: "10px 20px", fontSize: 14, fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {loading ? "…" : "Analyze"}
        </button>
      </div>

      {result && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Score */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            <MetricCard label="Impact Score" value={`${result.impact_score.toFixed(0)}%`}
              color={result.impact_score > 50 ? COLORS.red : result.impact_score > 20 ? COLORS.orange : COLORS.green} />
            <MetricCard label="Files Affected" value={result.affected_count} color={COLORS.cyan} />
            <MetricCard label="Blast Radius" value={`${result.impact_percentage.toFixed(1)}%`}
              sub="of codebase" color={COLORS.purple} />
          </div>

          {/* Direct */}
          {result.directly_affected.length > 0 && (
            <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
              <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>
                DIRECTLY AFFECTED ({result.directly_affected.length})
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {result.directly_affected.slice(0, 20).map((f) => (
                  <span key={f} style={{
                    background: `${COLORS.orange}15`, color: COLORS.orange,
                    border: `1px solid ${COLORS.orange}30`, borderRadius: 4,
                    padding: "3px 8px", fontSize: 11, fontFamily: "monospace",
                  }}>{f.split("/").pop()}</span>
                ))}
              </div>
            </div>
          )}

          {/* Transitive */}
          {result.transitively_affected.length > 0 && (
            <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
              <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>
                TRANSITIVELY AFFECTED ({result.transitively_affected.length})
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {result.transitively_affected.slice(0, 30).map((f) => (
                  <span key={f} style={{
                    background: `${COLORS.red}10`, color: COLORS.textSecondary,
                    border: `1px solid ${COLORS.border}`, borderRadius: 4,
                    padding: "3px 8px", fontSize: 11, fontFamily: "monospace",
                  }}>{f.split("/").pop()}</span>
                ))}
                {result.transitively_affected.length > 30 && (
                  <span style={{ color: COLORS.textDim, fontSize: 11 }}>
                    +{result.transitively_affected.length - 30} more
                  </span>
                )}
              </div>
            </div>
          )}

          {result.directly_affected.length === 0 && result.transitively_affected.length === 0 && (
            <div style={{ color: COLORS.green, background: `${COLORS.green}10`, border: `1px solid ${COLORS.green}30`, borderRadius: 8, padding: 16, fontSize: 14 }}>
              ✓ No files depend on this file — safe to change.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReportView({ repoId }: { repoId: string }) {
  const [report, setReport] = useState<ArchReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    apiGet<ArchReport>(`/repositories/${repoId}/report`)
      .then(setReport)
      .finally(() => setLoading(false));
  }, [repoId]);

  if (loading) return <Spinner />;
  if (!report) return null;

  return (
    <div style={{ padding: 32, maxWidth: 900 }}>
      <h2 style={{ color: COLORS.textPrimary, fontSize: 22, fontWeight: 700, marginBottom: 6 }}>Architecture Report</h2>
      <p style={{ color: COLORS.textSecondary, fontSize: 14, marginBottom: 28 }}>
        Scored by cycle count, coupling, density, and dead code.
      </p>

      {/* Health + metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 24, marginBottom: 28, background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24 }}>
        <HealthRing score={report.health_score} label={report.health_label} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, alignContent: "center" }}>
          <MetricCard label="Files" value={report.metrics.node_count ?? 0} color={COLORS.accent} />
          <MetricCard label="Dependencies" value={report.metrics.edge_count ?? 0} color={COLORS.cyan} />
          <MetricCard label="Cycles" value={report.metrics.cycle_count ?? 0}
            color={report.metrics.cycle_count > 0 ? COLORS.red : COLORS.green} />
          <MetricCard label="Hotspots" value={report.metrics.hotspot_count ?? 0}
            color={report.metrics.hotspot_count > 0 ? COLORS.orange : COLORS.green} />
          <MetricCard label="Density" value={`${((report.metrics.graph_density ?? 0) * 100).toFixed(2)}%`} color={COLORS.purple} />
          <MetricCard label="Coupling" value={`${(report.metrics.coupling_score ?? 0).toFixed(0)}/100`}
            color={report.metrics.coupling_score > 50 ? COLORS.red : COLORS.yellow} />
        </div>
      </div>

      {/* Risks */}
      {report.risks.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>
            RISK FINDINGS ({report.risks.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {report.risks.map((risk, i) => (
              <div key={i} style={{
                background: COLORS.surface, border: `1px solid ${COLORS.border}`,
                borderRadius: 10, overflow: "hidden",
              }}>
                <button
                  onClick={() => setExpanded(expanded === i ? null : i)}
                  style={{
                    width: "100%", background: "none", border: "none", cursor: "pointer",
                    padding: "14px 16px", display: "flex", alignItems: "flex-start",
                    gap: 12, textAlign: "left",
                  }}
                >
                  <RiskBadge severity={risk.severity} />
                  <span style={{ color: COLORS.textPrimary, fontSize: 14, fontWeight: 500, flex: 1 }}>{risk.title}</span>
                  <span style={{ color: COLORS.textDim, fontSize: 12 }}>{expanded === i ? "▲" : "▼"}</span>
                </button>
                {expanded === i && (
                  <div style={{ padding: "0 16px 16px", borderTop: `1px solid ${COLORS.border}`, paddingTop: 14 }}>
                    <p style={{ color: COLORS.textSecondary, fontSize: 13, marginBottom: 12, lineHeight: 1.6 }}>
                      {risk.description}
                    </p>
                    <div style={{ background: `${COLORS.green}10`, border: `1px solid ${COLORS.green}20`, borderRadius: 6, padding: 12, marginBottom: 12 }}>
                      <div style={{ color: COLORS.green, fontSize: 11, fontWeight: 600, marginBottom: 4 }}>RECOMMENDATION</div>
                      <p style={{ color: COLORS.textSecondary, fontSize: 13, lineHeight: 1.6, margin: 0 }}>{risk.recommendation}</p>
                    </div>
                    {risk.affected_files.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {risk.affected_files.slice(0, 8).map((f) => (
                          <span key={f} style={{
                            background: COLORS.bg, color: COLORS.textDim,
                            border: `1px solid ${COLORS.border}`, borderRadius: 4,
                            padding: "2px 7px", fontSize: 10, fontFamily: "monospace",
                          }}>{f.split("/").pop()}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Decomposition */}
      {report.decomposition_suggestions.length > 0 && (
        <div>
          <div style={{ color: COLORS.textSecondary, fontSize: 11, letterSpacing: "0.08em", marginBottom: 12 }}>
            DECOMPOSITION SUGGESTIONS
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {report.decomposition_suggestions.map((s, i) => (
              <div key={i} style={{
                background: COLORS.surface, border: `1px solid ${COLORS.border}`,
                borderRadius: 10, padding: 16, display: "flex", gap: 14,
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 8, background: `${COLORS.purple}20`,
                  border: `1px solid ${COLORS.purple}40`, display: "flex",
                  alignItems: "center", justifyContent: "center", flexShrink: 0, fontSize: 16,
                }}>
                  {s.type === "bounded_context" ? "⬡" : "⬢"}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ color: COLORS.textPrimary, fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{s.title}</div>
                  <div style={{ color: COLORS.textSecondary, fontSize: 13 }}>{s.description}</div>
                  <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: s.confidence === "high" ? COLORS.green : COLORS.yellow, fontSize: 11, fontWeight: 600 }}>
                      {s.confidence.toUpperCase()} CONFIDENCE
                    </span>
                    <span style={{ color: COLORS.textDim, fontSize: 11 }}>{s.files.length} files</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ChatView({ repoId, repoName }: { repoId: string; repoName: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: `Hello! I'm the ArchPilot AI analyst for **${repoName}**. I can explain architecture patterns, identify risks, and suggest refactoring strategies — all grounded in the dependency graph analysis.\n\nTry asking:\n- "What are the highest-risk files?"\n- "Which modules are tightly coupled?"\n- "How should I start decomposing this codebase?"`,
      grounded_in: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput("");

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: question,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const response = await apiPost<{ answer: string; grounded_in: string[] }>(
        `/repositories/${repoId}/chat`,
        { repository_id: repoId, question }
      );
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: response.answer,
          grounded_in: response.grounded_in,
        },
      ]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: `Error: ${e.message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const suggestions = [
    "What are the riskiest files?",
    "Are there circular dependencies?",
    "How tightly coupled is this codebase?",
    "Suggest a refactoring plan",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 100px)" }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: 28 }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
          {messages.map((msg) => (
            <div key={msg.id} style={{
              display: "flex", gap: 12,
              flexDirection: msg.role === "user" ? "row-reverse" : "row",
            }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                background: msg.role === "user" ? COLORS.accentGlow : "#8b5cf620",
                border: `1px solid ${msg.role === "user" ? COLORS.accent : COLORS.purple}40`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, marginTop: 2,
              }}>
                {msg.role === "user" ? "U" : "A"}
              </div>
              <div style={{
                maxWidth: "80%",
                background: msg.role === "user" ? `${COLORS.accent}15` : COLORS.surface,
                border: `1px solid ${msg.role === "user" ? COLORS.accent + "30" : COLORS.border}`,
                borderRadius: 10, padding: "12px 16px",
              }}>
                <div style={{
                  color: COLORS.textPrimary, fontSize: 14, lineHeight: 1.65,
                  whiteSpace: "pre-wrap",
                }}>
                  {msg.content}
                </div>
                {msg.grounded_in && msg.grounded_in.length > 0 && (
                  <div style={{ marginTop: 8, display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {msg.grounded_in.map((source) => (
                      <span key={source} style={{
                        color: COLORS.textDim, fontSize: 9, fontFamily: "monospace",
                        background: COLORS.bg, border: `1px solid ${COLORS.border}`,
                        borderRadius: 3, padding: "1px 5px",
                      }}>
                        {source}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ display: "flex", gap: 5, padding: "10px 44px" }}>
              {[0, 1, 2].map((i) => (
                <div key={i} style={{
                  width: 6, height: 6, borderRadius: "50%", background: COLORS.textDim,
                  animation: `bounce 1s ${i * 0.2}s infinite`,
                }} />
              ))}
              <style>{`@keyframes bounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }`}</style>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Suggestions */}
      {messages.length === 1 && (
        <div style={{ padding: "0 28px 12px" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
            {suggestions.map((s) => (
              <button key={s} onClick={() => setInput(s)} style={{
                background: COLORS.surface, border: `1px solid ${COLORS.border}`,
                color: COLORS.textSecondary, borderRadius: 6, padding: "6px 12px",
                fontSize: 12, cursor: "pointer",
              }}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{ borderTop: `1px solid ${COLORS.border}`, padding: 16 }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", gap: 10 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Ask about architecture, risks, dependencies…"
            disabled={loading}
            style={{
              flex: 1, background: COLORS.surface, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, padding: "10px 14px", color: COLORS.textPrimary,
              fontSize: 14, outline: "none",
            }}
            onFocus={(e) => (e.target.style.borderColor = COLORS.accent)}
            onBlur={(e) => (e.target.style.borderColor = COLORS.border)}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            style={{
              background: COLORS.accent, color: "#fff", border: "none",
              borderRadius: 8, padding: "10px 20px", fontSize: 14, fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [view, setView] = useState<View>("home");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  // Load existing repos on mount
  useEffect(() => {
    apiGet<Repository[]>("/repositories").then(setRepos).catch(() => {});
  }, []);

  const handleAnalyze = useCallback(async (url: string) => {
    setLoading(true);
    setError(undefined);
    try {
      const repo = await apiPost<Repository>("/repositories/analyze", { url });
      setRepos((prev) => {
        const without = prev.filter((r) => r.id !== repo.id);
        return [repo, ...without];
      });
      setSelectedRepo(repo);
      setView("report");
    } catch (e: any) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelectRepo = useCallback((repo: Repository) => {
    setSelectedRepo(repo);
    setView("report");
  }, []);

  const handleBack = () => {
    setSelectedRepo(null);
    setView("home");
  };

  return (
    <div style={{ background: COLORS.bg, minHeight: "100vh", color: COLORS.textPrimary, fontFamily: "system-ui, -apple-system, sans-serif" }}>
      {/* Header */}
      <header style={{
        borderBottom: `1px solid ${COLORS.border}`,
        background: `${COLORS.surface}cc`,
        backdropFilter: "blur(12px)",
        position: "sticky", top: 0, zIndex: 100,
        height: 52,
      }}>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "0 20px", height: "100%", display: "flex", alignItems: "center", gap: 16 }}>
          {/* Logo */}
          <button onClick={handleBack} style={{ background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 8, padding: 0 }}>
            <div style={{
              width: 28, height: 28, background: `linear-gradient(135deg, ${COLORS.accent}, ${COLORS.purple})`,
              borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, boxShadow: `0 0 12px ${COLORS.accent}40`,
            }}>⬡</div>
            <span style={{ color: COLORS.textPrimary, fontSize: 15, fontWeight: 700, letterSpacing: "-0.02em" }}>
              Arch<span style={{ color: COLORS.accent }}>Pilot</span>
            </span>
          </button>

          {/* Repo context + nav */}
          {selectedRepo && (
            <>
              <div style={{ width: 1, height: 20, background: COLORS.border }} />
              <span style={{ color: COLORS.textSecondary, fontSize: 13, fontFamily: "monospace" }}>
                {selectedRepo.owner}/{selectedRepo.name}
              </span>
              <div style={{ height: 20, width: 1, background: COLORS.border }} />
              <nav style={{ display: "flex", gap: 2, flex: 1 }}>
                <NavButton active={view === "report"} onClick={() => setView("report")}>📊 Report</NavButton>
                <NavButton active={view === "graph"} onClick={() => setView("graph")}>⬡ Graph</NavButton>
                <NavButton active={view === "impact"} onClick={() => setView("impact")}>💥 Impact</NavButton>
                <NavButton active={view === "chat"} onClick={() => setView("chat")}>🤖 AI Chat</NavButton>
              </nav>
              <StatusBadge status={selectedRepo.status} />
            </>
          )}

          {!selectedRepo && <div style={{ flex: 1 }} />}

          <a
            href="http://localhost:8000/docs"
            target="_blank"
            style={{ color: COLORS.textDim, fontSize: 12, textDecoration: "none" }}
          >
            API Docs ↗
          </a>
        </div>
      </header>

      {/* Main content */}
      <main>
        {view === "home" && (
          <HomeView
            onAnalyze={handleAnalyze}
            repos={repos}
            onSelectRepo={handleSelectRepo}
            loading={loading}
            error={error}
          />
        )}
        {selectedRepo && view === "graph" && <GraphView repoId={selectedRepo.id} />}
        {selectedRepo && view === "impact" && <ImpactView repoId={selectedRepo.id} />}
        {selectedRepo && view === "report" && <ReportView repoId={selectedRepo.id} />}
        {selectedRepo && view === "chat" && <ChatView repoId={selectedRepo.id} repoName={`${selectedRepo.owner}/${selectedRepo.name}`} />}
      </main>
    </div>
  );
}
