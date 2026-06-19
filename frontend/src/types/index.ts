// ArchPilot Frontend Type Definitions
// Mirrors backend Pydantic schemas

export interface Repository {
  id: string;
  owner: string;
  name: string;
  url: string;
  description?: string;
  language?: string;
  stars: number;
  forks: number;
  status: "pending" | "processing" | "completed" | "failed";
  default_branch: string;
  created_at: string;
  updated_at: string;
}

export interface RepositorySummary {
  repository: Repository;
  file_count: number;
  dependency_count: number;
  languages: Record<string, number>;
  has_analysis: boolean;
}

// Graph Types
export interface GraphNode {
  id: string;
  path: string;
  file_type: string;
  fan_in: number;
  fan_out: number;
  is_entry_point: boolean;
  is_dead_code: boolean;
  centrality_score: number;
  in_cycle: boolean;
}

export interface DependencyEdge {
  source: string;
  target: string;
  import_statement?: string;
}

export interface DependencyGraph {
  repository_id: string;
  nodes: GraphNode[];
  edges: DependencyEdge[];
  adjacency_list: Record<string, string[]>;
  node_count: number;
  edge_count: number;
}

// Impact Analysis
export interface ImpactAnalysis {
  file_path: string;
  directly_affected: string[];
  transitively_affected: string[];
  impact_score: number;
  affected_count: number;
  total_file_count: number;
  impact_percentage: number;
}

// Cycle Detection
export interface CycleDetection {
  repository_id: string;
  has_cycles: boolean;
  cycles: string[][];
  cycle_count: number;
  files_in_cycles: string[];
}

// SCC
export interface SCCResult {
  repository_id: string;
  components: string[][];
  component_count: number;
  largest_scc_size: number;
  tightly_coupled_modules: string[][];
}

// Topological Sort
export interface TopologicalSort {
  repository_id: string;
  order: string[];
  has_cycles: boolean;
  cycle_groups: string[][];
}

// Graph Metrics
export interface GraphMetrics {
  repository_id: string;
  most_depended_on: Array<{ path: string; fan_in: number; centrality: number }>;
  most_dependent: Array<{ path: string; fan_out: number }>;
  orphan_files: string[];
  entry_points: string[];
  dead_files: string[];
  average_fan_in: number;
  average_fan_out: number;
  graph_density: number;
  coupling_score: number;
}

// Architecture Report
export type RiskSeverity = "critical" | "high" | "medium" | "low";
export type RiskCategory =
  | "circular_dependency"
  | "hotspot"
  | "tight_coupling"
  | "dead_code"
  | "high_density";

export interface ArchitectureRisk {
  severity: RiskSeverity;
  category: RiskCategory;
  title: string;
  description: string;
  affected_files: string[];
  recommendation: string;
}

export interface DecompositionSuggestion {
  type: "bounded_context" | "api_boundary";
  title: string;
  description: string;
  files: string[];
  confidence: "high" | "medium" | "low";
}

export interface ArchitectureReport {
  repository_id: string;
  health_score: number;
  health_label: "Excellent" | "Good" | "Fair" | "Poor" | "Critical";
  risks: ArchitectureRisk[];
  metrics: {
    node_count: number;
    edge_count: number;
    graph_density: number;
    coupling_score: number;
    cycle_count: number;
    scc_count: number;
    large_scc_count: number;
    entry_points: number;
    orphan_files: number;
    hotspot_count: number;
    average_fan_in: number;
    average_fan_out: number;
  };
  decomposition_suggestions: DecompositionSuggestion[];
  generated_at: string;
}

// Tree
export interface TreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  file_type?: string;
  children: TreeNode[];
  size_bytes: number;
  has_dependencies: boolean;
}

export interface RepositoryTree {
  repository_id: string;
  tree: TreeNode;
  total_files: number;
  total_dirs: number;
}

// AI Chat
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  grounded_in?: string[];
  timestamp: string;
}

export interface AIChatResponse {
  answer: string;
  grounded_in: string[];
  repository_id: string;
}

// Analysis Status
export interface AnalysisStatus {
  repository_id: string;
  status: string;
  completed_analyses: string[];
  pending_analyses: string[];
  error_message?: string;
}
