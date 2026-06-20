import axios, { type AxiosInstance } from "axios";
import type {
  AIChatResponse,
  ArchitectureReport,
  CycleDetection,
  DependencyGraph,
  GraphMetrics,
  ImpactAnalysis,
  Repository,
  RepositorySummary,
  RepositoryTree,
  SCCResult,
  TopologicalSort,
} from "../types";

const BASE_URL ="https://arch-pilot.onrender.com";

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 120_000, // 2 min — analysis takes time
});

// ─── Repository ───────────────────────────────────────────────────────────────

export const analyzeRepository = async (url: string): Promise<Repository> => {
  const { data } = await api.post("/repositories/analyze", { url });
  return data;
};

export const listRepositories = async (): Promise<Repository[]> => {
  const { data } = await api.get("/repositories");
  return data;
};

export const getRepository = async (id: string): Promise<Repository> => {
  const { data } = await api.get(`/repositories/${id}`);
  return data;
};

export const getRepositorySummary = async (
  id: string
): Promise<RepositorySummary> => {
  const { data } = await api.get(`/repositories/${id}/summary`);
  return data;
};

export const getRepositoryTree = async (id: string): Promise<RepositoryTree> => {
  const { data } = await api.get(`/repositories/${id}/tree`);
  return data;
};

// ─── Graph Analysis ───────────────────────────────────────────────────────────

export const getDependencyGraph = async (
  id: string
): Promise<DependencyGraph> => {
  const { data } = await api.get(`/repositories/${id}/graph`);
  return data;
};

export const analyzeImpact = async (
  repositoryId: string,
  filePath: string,
  maxDepth: number = 10
): Promise<ImpactAnalysis> => {
  const { data } = await api.post(`/repositories/${repositoryId}/impact`, {
    repository_id: repositoryId,
    file_path: filePath,
    max_depth: maxDepth,
  });
  return data;
};

export const detectCycles = async (id: string): Promise<CycleDetection> => {
  const { data } = await api.get(`/repositories/${id}/cycles`);
  return data;
};

export const getSCC = async (id: string): Promise<SCCResult> => {
  const { data } = await api.get(`/repositories/${id}/scc`);
  return data;
};

export const getTopologicalSort = async (
  id: string
): Promise<TopologicalSort> => {
  const { data } = await api.get(`/repositories/${id}/topo-sort`);
  return data;
};

export const getGraphMetrics = async (id: string): Promise<GraphMetrics> => {
  const { data } = await api.get(`/repositories/${id}/metrics`);
  return data;
};

// ─── Intelligence ─────────────────────────────────────────────────────────────

export const getArchitectureReport = async (
  id: string
): Promise<ArchitectureReport> => {
  const { data } = await api.get(`/repositories/${id}/report`);
  return data;
};

export const sendChatMessage = async (
  repositoryId: string,
  question: string,
  contextFilePath?: string
): Promise<AIChatResponse> => {
  const { data } = await api.post(`/repositories/${repositoryId}/chat`, {
    repository_id: repositoryId,
    question,
    context_file_path: contextFilePath,
  });
  return data;
};
