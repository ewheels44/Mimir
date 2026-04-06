// API response types for metrics endpoints

export interface MetricsSummary {
  total_queries: number;
  total_cost: number;
  traditional_cost: number;
  savings: number;
  savings_percent: number;
  by_type: Record<string, { count: number; cost: number }>;
}

export interface DailyMetrics {
  date: string;
  cost: number;
  traditional_cost: number;
  queries: number;
}

export interface QueryBreakdown {
  query_type: string;
  count: number;
  cost: number;
  embedding_cost: number;
  llm_input_cost: number;
  llm_output_cost: number;
}

export interface ComponentCosts {
  embedding_cost: number;
  llm_input_cost: number;
  llm_output_cost: number;
  total_cost: number;
}

// Traditional token estimates per query type
export const TRADITIONAL_TOKENS: Record<string, number> = {
  search: 3000,
  query: 8000,
  rag: 12000,
  agent: 15000,
};
