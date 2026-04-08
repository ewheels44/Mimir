// API response types for metrics endpoints

export interface MetricsSummary {
  total_queries: number;
  total_cost: number;
  avg_cost_per_query: number;
  total_tokens_in: number;
  total_tokens_out: number;
  traditional_cost: number;
  savings: number;
  savings_percent: number;
  time_saved_secs: number;
  by_type: Record<string, TypeSummary>;
}

export interface TypeSummary {
  count: number;
  total_cost: number;
  avg_cost: number;
  total_tokens_in: number;
  total_tokens_out: number;
  avg_duration_ms: number;
  avg_docs_retrieved: number;
}

export interface DailyMetrics {
  date: string;
  queries: number;
  cost: number;
  traditional_cost: number;
  tokens_in: number;
  tokens_out: number;
}

export interface QueryBreakdown {
  query_type: string;
  count: number;
  cost: number;
  avg_cost: number;
  embedding_cost: number;
  llm_input_cost: number;
  llm_output_cost: number;
  traditional_cost: number;
  savings: number;
}

export interface ComponentCosts {
  embedding_cost: number;
  llm_input_cost: number;
  llm_output_cost: number;
  total_cost: number;
  count: number;
}

// Traditional token estimates per query type
export const TRADITIONAL_TOKENS: Record<string, number> = {
  search: 3000,
  query: 8000,
  rag: 12000,
  agent: 15000,
};
