use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use clap::Parser;
use tokio::sync::RwLock;
use tower_http::{cors::CorsLayer, services::ServeDir};
use tracing_subscriber::EnvFilter;

mod graph;
mod metrics;
mod models;
mod proxy;
mod sidecar;

use graph::GraphCache;
use models::*;

// ── CLI / config ──────────────────────────────────────────────────────────────

#[derive(Parser, Debug, Clone)]
#[command(name = "mimir-web", about = "Mimir Web UI — Rust/React rewrite")]
struct Args {
    /// Project root directory (falls back to PROJECT_ROOT env var, then cwd)
    #[arg(long, env = "PROJECT_ROOT")]
    project: Option<PathBuf>,

    /// LlamaIndex knowledge directory (falls back to KNOWLEDGE_DIR env var)
    #[arg(long, env = "KNOWLEDGE_DIR")]
    knowledge_dir: Option<PathBuf>,

    /// Port for this server
    #[arg(long, default_value = "8000")]
    port: u16,

    /// Bind host
    #[arg(long, default_value = "0.0.0.0")]
    host: String,

    /// Internal port for the Python sidecar
    #[arg(long, default_value = "18001")]
    sidecar_port: u16,
}

// ── Shared application state ──────────────────────────────────────────────────

#[derive(Clone)]
pub struct AppState {
    pub knowledge_dir: PathBuf,
    pub project_root: PathBuf,
    pub graph_cache: Arc<RwLock<GraphCache>>,
    pub sidecar_port: u16,
}

// ── Entry point ───────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("mimir_web=info,warn")),
        )
        .init();

    let args = Args::parse();

    let project_root = args
        .project
        .unwrap_or_else(|| std::env::current_dir().unwrap());

    let knowledge_dir = args.knowledge_dir.unwrap_or_else(|| {
        project_root.join(".knowledge").join("llamaindex")
    });

    tracing::info!("project_root:  {}", project_root.display());
    tracing::info!("knowledge_dir: {}", knowledge_dir.display());

    // Spawn Python sidecar (LlamaIndex search/query)
    let _sidecar = sidecar::spawn(&project_root, args.sidecar_port).await?;

    let state = AppState {
        knowledge_dir,
        project_root,
        graph_cache: Arc::new(RwLock::new(GraphCache::default())),
        sidecar_port: args.sidecar_port,
    };

    // Serve the React build from ../client/dist
    let client_dist = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .join("client")
        .join("dist");

    let app = Router::new()
        // ── Graph ──────────────────────────────────────────────────────────
        .route("/api/graph", get(api_graph))
        .route("/api/graph/edges", get(api_graph_edges))
        .route("/api/graph/cache-key", get(api_cache_key))
        .route("/api/graph/invalidate", post(api_invalidate))
        .route("/api/graph/module/{module_id}/children", get(api_module_children))
        .route("/api/graph/path", get(api_graph_path))
        .route("/api/graph/neighbors", get(api_graph_neighbors))
        .route("/api/graph/stats", get(api_graph_stats))
        // ── Metrics ────────────────────────────────────────────────────────
        .route("/api/metrics/summary", get(api_metrics_summary))
        .route("/api/metrics/daily", get(api_metrics_daily))
        .route("/api/metrics/breakdown", get(api_metrics_breakdown))
        .route("/api/metrics/components", get(api_metrics_components))
        // ── Search / query (proxied to Python sidecar) ─────────────────────
        .route("/api/search", post(api_search))
        .route("/api/query", post(api_query))
        .route("/api/stats", get(api_stats))
        // ── Static SPA ─────────────────────────────────────────────────────
        .fallback_service(
            ServeDir::new(&client_dist).append_index_html_on_directories(true),
        )
        .layer(CorsLayer::permissive())
        .with_state(state);

    let listener =
        tokio::net::TcpListener::bind(format!("{}:{}", args.host, args.port)).await?;
    tracing::info!(
        "Mimir Web UI listening on http://{}:{}",
        args.host,
        args.port
    );
    axum::serve(listener, app).await?;
    Ok(())
}

// ── Graph handlers ─────────────────────────────────────────────────────────────

/// Refresh the in-process graph cache if the source files have changed.
async fn ensure_cache(state: &AppState) -> Result<(), (StatusCode, String)> {
    let current_key = graph::cache_key(&state.knowledge_dir);
    {
        if state.graph_cache.read().await.cache_key == current_key {
            return Ok(());
        }
    }
    let fresh = graph::build_graph(&state.knowledge_dir)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    *state.graph_cache.write().await = fresh;
    Ok(())
}

async fn api_graph(
    State(state): State<AppState>,
    Query(params): Query<GraphQueryParams>,
) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let min_degree = params.min_degree.unwrap_or(0);
    let nodes = filtered_nodes(&cache, min_degree);

    if params.mode.as_deref() == Some("summary") {
        return Json(GraphResponse { nodes, edges: vec![] }).into_response();
    }

    let id_set: std::collections::HashSet<&str> =
        nodes.iter().map(|n| n.id.as_str()).collect();
    let edges = cache
        .edges
        .iter()
        .filter(|e| id_set.contains(e.source.as_str()) && id_set.contains(e.target.as_str()))
        .cloned()
        .collect();

    Json(GraphResponse { nodes, edges }).into_response()
}

async fn api_graph_edges(
    State(state): State<AppState>,
    Query(params): Query<DegreeParam>,
) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let min = params.min_degree.unwrap_or(0);
    let effective_min = if min == 0 { 1 } else { min };

    let edges: Vec<_> = cache
        .edges
        .iter()
        .filter(|e| {
            cache.degree.get(&e.source).copied().unwrap_or(0) >= effective_min
                && cache.degree.get(&e.target).copied().unwrap_or(0) >= effective_min
        })
        .collect();

    Json(serde_json::json!({ "edges": edges, "count": edges.len() })).into_response()
}

async fn api_cache_key(State(state): State<AppState>) -> impl IntoResponse {
    Json(graph::cache_key(&state.knowledge_dir))
}

async fn api_invalidate(State(state): State<AppState>) -> impl IntoResponse {
    state.graph_cache.write().await.cache_key.clear();
    Json(serde_json::json!({ "status": "cache cleared" }))
}

async fn api_module_children(
    State(state): State<AppState>,
    Path(module_id): Path<String>,
) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let (nodes, edges) = graph::get_module_children(&module_id, &cache);
    Json(GraphResponse { nodes, edges }).into_response()
}

async fn api_graph_path(
    State(state): State<AppState>,
    Query(params): Query<PathQueryParams>,
) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let result = graph::find_path(&params.source, &params.target, &cache);

    let steps: Vec<PathStepResponse> = result
        .steps
        .iter()
        .map(|s| PathStepResponse {
            node: s.node.clone(),
            label: s.label.clone(),
            file_path: s.file_path.clone(),
            edge_type: s.edge_type.clone(),
            edge_cost: s.edge_cost,
        })
        .collect();

    Json(PathResponse {
        found: result.found,
        source: params.source.clone(),
        target: params.target.clone(),
        total_cost: result.total_cost,
        hops: result.hops,
        steps,
    })
    .into_response()
}

async fn api_graph_neighbors(
    State(state): State<AppState>,
    Query(params): Query<NeighborQueryParams>,
) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let depth = params.depth.unwrap_or(1);
    let node_id = match &params.node_id {
        Some(id) => id.clone(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                "Missing required query param: node_id",
            )
                .into_response()
        }
    };
    let result =
        graph::find_neighbors(&node_id, depth, params.relation_type.as_deref(), &cache);

    let neighbors: Vec<NeighborEntryResponse> = result
        .neighbors
        .iter()
        .map(|n| NeighborEntryResponse {
            node: n.node.clone(),
            label: n.label.clone(),
            file_path: n.file_path.clone(),
            edge_type: n.edge_type.clone(),
            direction: n.direction.clone(),
        })
        .collect();

    Json(NeighborResponse {
        center: result.center,
        depth,
        relation_filter: params.relation_type,
        neighbors,
    })
    .into_response()
}

async fn api_graph_stats(State(state): State<AppState>) -> impl IntoResponse {
    if let Err((code, msg)) = ensure_cache(&state).await {
        return (code, msg).into_response();
    }
    let cache = state.graph_cache.read().await;
    let stats = graph::compute_stats(&cache);

    Json(StatsResponse {
        total_nodes: stats.total_nodes,
        total_edges: stats.total_edges,
        total_entities: stats.total_entities,
        by_relation_type: stats.by_relation_type,
        by_language: stats.by_language,
        top_connected: stats.top_connected,
    })
    .into_response()
}

fn filtered_nodes(
    cache: &GraphCache,
    min_degree: u32,
) -> Vec<crate::models::GraphNode> {
    let effective_min = if min_degree == 0 { 1 } else { min_degree };
    cache
        .nodes
        .iter()
        .filter(|n| {
            cache.degree.get(&n.id).copied().unwrap_or(0) >= effective_min
        })
        .cloned()
        .collect()
}

// ── Metrics handlers ──────────────────────────────────────────────────────────

async fn api_metrics_summary(
    State(state): State<AppState>,
    Query(p): Query<DaysParam>,
) -> impl IntoResponse {
    match metrics::get_summary(&state.project_root, p.days.unwrap_or(30)) {
        Ok(v) => Json(v).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn api_metrics_daily(
    State(state): State<AppState>,
    Query(p): Query<DaysParam>,
) -> impl IntoResponse {
    match metrics::get_daily(&state.project_root, p.days.unwrap_or(30)) {
        Ok(v) => Json(v).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn api_metrics_breakdown(
    State(state): State<AppState>,
    Query(p): Query<DaysParam>,
) -> impl IntoResponse {
    match metrics::get_breakdown(&state.project_root, p.days.unwrap_or(30)) {
        Ok(v) => Json(v).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn api_metrics_components(
    State(state): State<AppState>,
    Query(p): Query<DaysParam>,
) -> impl IntoResponse {
    match metrics::get_components(&state.project_root, p.days.unwrap_or(30)) {
        Ok(v) => Json(v).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

// ── Proxy handlers ────────────────────────────────────────────────────────────

async fn api_search(
    State(state): State<AppState>,
    Json(body): Json<serde_json::Value>,
) -> impl IntoResponse {
    proxy::forward_post(state.sidecar_port, "/internal/search", body).await
}

async fn api_query(
    State(state): State<AppState>,
    Json(body): Json<serde_json::Value>,
) -> impl IntoResponse {
    proxy::forward_post(state.sidecar_port, "/internal/query", body).await
}

async fn api_stats(State(state): State<AppState>) -> impl IntoResponse {
    proxy::forward_get(state.sidecar_port, "/internal/stats").await
}
