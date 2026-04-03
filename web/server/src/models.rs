use serde::{Deserialize, Serialize};

// ── Graph types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct NodeMetadata {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_size: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub creation_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_modified_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub function_count: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub class_count: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total_children: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub module_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub external: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line_number: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub label: String,
    #[serde(rename = "type")]
    pub node_type: String,
    pub metadata: NodeMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    pub id: String,
    pub source: String,
    pub target: String,
    pub label: String,
    #[serde(rename = "type")]
    pub edge_type: String,
}

#[derive(Debug, Serialize)]
pub struct GraphResponse {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

// ── Query params ─────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct GraphQueryParams {
    pub mode: Option<String>,
    pub min_degree: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct DegreeParam {
    pub min_degree: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct DaysParam {
    pub days: Option<u32>,
}

// ── Sidecar / proxy request bodies ───────────────────────────────────────────

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct SearchRequest {
    pub query: String,
    pub top_k: Option<u32>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct QueryRequest {
    pub question: String,
}
