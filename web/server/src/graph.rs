use anyhow::{Context, Result};
use serde::Deserialize;
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::path::Path;
use std::time::SystemTime;

use crate::models::{GraphEdge, GraphNode, NodeMetadata};

// ── Docstore deserialization ──────────────────────────────────────────────────

#[derive(Deserialize)]
struct DocstoreFile {
    #[serde(rename = "docstore/data", default)]
    data: HashMap<String, DocEntry>,
    #[serde(rename = "docstore/docs", default)]
    docs: HashMap<String, DocEntry>,
    // We ignore docstore/metadata (just hashes + ref_doc_ids) for now
}

#[derive(Deserialize)]
struct DocEntry {
    #[serde(rename = "__data__")]
    inner: DocData,
}

#[derive(Deserialize)]
struct DocData {
    #[allow(dead_code)]
    id_: String,
    metadata: DocMetadata,
}

#[derive(Deserialize, Clone, Default)]
struct DocMetadata {
    file_path: Option<String>,
    file_name: Option<String>,
    file_type: Option<String>,
    file_size: Option<u64>,
    creation_date: Option<String>,
    last_modified_date: Option<String>,
}

// ── Relationships deserialization ─────────────────────────────────────────────

#[derive(Deserialize, Default)]
struct RelationshipsFile {
    #[serde(default)]
    relationships: Vec<Relationship>,
    #[serde(default)]
    entities: HashMap<String, RawEntity>,
}

#[derive(Deserialize)]
struct Relationship {
    source: String,
    target: String,
    relation_type: String,
}

#[derive(Deserialize)]
struct RawEntity {
    file_path: Option<String>,
    entity_type: Option<String>,
    name: Option<String>,
    line_number: Option<u32>,
    #[serde(default)]
    metadata: HashMap<String, serde_json::Value>,
}

// ── Public cache types ────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct EntityData {
    pub file_path: String,
    pub entity_type: String,
    pub name: String,
    pub line_number: Option<u32>,
    pub class_name: Option<String>,
}

#[derive(Debug, Default)]
pub struct GraphCache {
    pub cache_key: String,
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
    pub degree: HashMap<String, u32>,
    pub file_path_to_id: HashMap<String, String>,
    pub entities: HashMap<String, EntityData>,
    pub positions: HashMap<String, (f64, f64)>,
}

// ── Cache key (mtime fingerprint) ─────────────────────────────────────────────

pub fn cache_key(knowledge_dir: &Path) -> String {
    let docstore = knowledge_dir.join("docstore.json");
    let rels = knowledge_dir
        .parent()
        .map(|p| p.join("code_relationships.json"))
        .unwrap_or_default();

    let mtime_str = |p: &Path| -> String {
        p.metadata()
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
            .map(|d| format!("{}:{}", p.display(), d.as_nanos()))
            .unwrap_or_else(|| format!("{}:missing", p.display()))
    };

    format!("{}|{}", mtime_str(&docstore), mtime_str(&rels))
}

// ── Main graph builder ────────────────────────────────────────────────────────

pub fn build_graph(knowledge_dir: &Path) -> Result<GraphCache> {
    let t_total = std::time::Instant::now();
    let key = cache_key(knowledge_dir);

    // ── Parse docstore ───────────────────────────────────────────────────────
    let docstore_path = knowledge_dir.join("docstore.json");
    let raw = std::fs::read_to_string(&docstore_path)
        .with_context(|| format!("reading {}", docstore_path.display()))?;
    let docstore: DocstoreFile =
        serde_json::from_str(&raw).with_context(|| "parsing docstore.json")?;

    // Prefer docstore/data, fall back to docstore/docs
    let doc_entries = if !docstore.data.is_empty() {
        docstore.data
    } else {
        docstore.docs
    };

    let mut nodes: Vec<GraphNode> = Vec::new();
    let mut file_path_to_id: HashMap<String, String> = HashMap::new();

    for (doc_id, entry) in &doc_entries {
        let meta = &entry.inner.metadata;
        let file_path = meta
            .file_path
            .clone()
            .or_else(|| meta.file_name.clone())
            .unwrap_or_else(|| "unknown".to_string());

        // Deduplicate by file_path — first occurrence wins
        if file_path_to_id.contains_key(&file_path) {
            continue;
        }
        file_path_to_id.insert(file_path.clone(), doc_id.clone());

        let file_name = meta.file_name.clone().unwrap_or_else(|| {
            Path::new(&file_path)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| file_path.clone())
        });

        let node_type = if is_code_file(&file_name) {
            "code"
        } else {
            "document"
        };

        nodes.push(GraphNode {
            id: doc_id.clone(),
            label: file_name,
            node_type: node_type.to_string(),
            metadata: NodeMetadata {
                file_path: meta.file_path.clone(),
                file_name: meta.file_name.clone(),
                file_type: meta.file_type.clone(),
                file_size: meta.file_size,
                creation_date: meta.creation_date.clone(),
                last_modified_date: meta.last_modified_date.clone(),
                ..Default::default()
            },
            position: None,
        });
    }

    // ── Load relationships + entities ────────────────────────────────────────
    let rel_path = knowledge_dir
        .parent()
        .map(|p| p.join("code_relationships.json"))
        .unwrap_or_default();

    let rel_file: RelationshipsFile = if rel_path.exists() {
        let raw = std::fs::read_to_string(&rel_path).unwrap_or_default();
        serde_json::from_str(&raw).unwrap_or_default()
    } else {
        RelationshipsFile::default()
    };

    // Convert raw entities
    let mut entities: HashMap<String, EntityData> = HashMap::new();
    for (key, ent) in &rel_file.entities {
        let (Some(fp), Some(et)) = (ent.file_path.as_ref(), ent.entity_type.as_ref()) else {
            continue;
        };
        let class_name = ent
            .metadata
            .get("class")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
        entities.insert(
            key.clone(),
            EntityData {
                file_path: fp.clone(),
                entity_type: et.clone(),
                name: ent
                    .name
                    .clone()
                    .unwrap_or_else(|| key.split("::").last().unwrap_or(key).to_string()),
                line_number: ent.line_number,
                class_name,
            },
        );
    }

    // Annotate code nodes with child counts
    for node in &mut nodes {
        if node.node_type != "code" {
            continue;
        }
        let node_fp = node.metadata.file_path.as_deref().unwrap_or("");
        let node_fn = node.metadata.file_name.as_deref().unwrap_or("");
        let mut fc = 0u32;
        let mut cc = 0u32;
        for ent in entities.values() {
            if ent.file_path == node_fp || ent.file_path == node_fn {
                match ent.entity_type.as_str() {
                    "function" => fc += 1,
                    "class" => cc += 1,
                    _ => {}
                }
            }
        }
        node.metadata.function_count = Some(fc);
        node.metadata.class_count = Some(cc);
        node.metadata.total_children = Some(fc + cc);
    }

    // ── Build suffix index + edges ────────────────────────────────────────────
    let suffix_idx = build_suffix_index(&file_path_to_id);
    let existing_ids: HashSet<String> = nodes.iter().map(|n| n.id.clone()).collect();

    let mut edges: Vec<GraphEdge> = Vec::new();
    let mut ext_ids: HashSet<String> = HashSet::new();
    let mut ext_nodes: Vec<GraphNode> = Vec::new();

    for rel in &rel_file.relationships {
        // Resolve source: try suffix lookup first, then entity file path
        let source_id = match lookup_suffix(&rel.source, &suffix_idx) {
            Some(id) => id,
            None => {
                // Try extracting file path from entity key (e.g., "src/mimir/config.py::MimirConfig" → file path)
                let source_path = if rel.source.contains("::") {
                    rel.source.split("::").next().unwrap_or(&rel.source).to_string()
                } else {
                    rel.source.clone()
                };
                // Try to find the file path in the suffix index
                if let Some(id) = lookup_suffix(&source_path, &suffix_idx) {
                    id
                } else if !rel.source.starts_with("external:") {
                    // Create an external node for internal entity that has no docstore entry
                    let ext_id = format!("entity:{}", rel.source.replace("::", "."));
                    if !existing_ids.contains(&ext_id) && ext_ids.insert(ext_id.clone()) {
                        let label = rel.source.split("::").last().unwrap_or(&rel.source).to_string();
                        ext_nodes.push(GraphNode {
                            id: ext_id.clone(),
                            label,
                            node_type: if rel.source.contains("::class") { "class".to_string() } else { "entity".to_string() },
                            metadata: NodeMetadata {
                                module_path: Some(rel.source.clone()),
                                external: Some(false),
                                ..Default::default()
                            },
                            position: None,
                        });
                    }
                    ext_id
                } else {
                    continue; // Skip if we can't resolve and it's marked as external
                }
            }
        };

        // Resolve target similarly
        let target_id = match lookup_suffix(&rel.target, &suffix_idx) {
            Some(id) => id,
            None => {
                let target_path = if rel.target.contains("::") {
                    rel.target.split("::").next().unwrap_or(&rel.target).to_string()
                } else {
                    rel.target.clone()
                };
                if let Some(id) = lookup_suffix(&target_path, &suffix_idx) {
                    id
                } else if !rel.target.starts_with("external:") {
                    let ext_id = format!("entity:{}", rel.target.replace("::", "."));
                    if !existing_ids.contains(&ext_id) && ext_ids.insert(ext_id.clone()) {
                        let label = rel.target.split("::").last().unwrap_or(&rel.target).to_string();
                        ext_nodes.push(GraphNode {
                            id: ext_id.clone(),
                            label,
                            node_type: if rel.target.contains("::class") { "class".to_string() } else { "entity".to_string() },
                            metadata: NodeMetadata {
                                module_path: Some(rel.target.clone()),
                                external: Some(false),
                                ..Default::default()
                            },
                            position: None,
                        });
                    }
                    ext_id
                } else {
                    continue;
                }
            }
        };

        let src_short = &source_id[..source_id.len().min(8)];
        let tgt_short = &target_id[..target_id.len().min(8)];
        let rel_short = &rel.relation_type[..rel.relation_type.len().min(4)];

        edges.push(GraphEdge {
            id: format!("e-{}-{}-{}", src_short, tgt_short, rel_short),
            source: source_id,
            target: target_id,
            label: rel.relation_type.replace('_', " "),
            edge_type: rel.relation_type.clone(),
        });
    }

    nodes.extend(ext_nodes);

    // ── Degree map ────────────────────────────────────────────────────────────
    let mut degree: HashMap<String, u32> = HashMap::new();
    for edge in &edges {
        *degree.entry(edge.source.clone()).or_insert(0) += 1;
        *degree.entry(edge.target.clone()).or_insert(0) += 1;
    }

    // ── Pre-compute layout positions ───────────────────────────────────────
    let positions = compute_layout(&nodes, &edges);
    for node in &mut nodes {
        if let Some(&(x, y)) = positions.get(&node.id) {
            node.position = Some(crate::models::NodePosition { x, y });
        }
    }

    tracing::info!(
        "build_graph total: {:.1?} ({} nodes, {} edges)",
        t_total.elapsed(),
        nodes.len(),
        edges.len()
    );

    Ok(GraphCache {
        cache_key: key,
        nodes,
        edges,
        degree,
        file_path_to_id,
        entities,
        positions,
    })
}

// ── Module children ───────────────────────────────────────────────────────────

pub fn get_module_children(
    module_id: &str,
    cache: &GraphCache,
) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let Some(file_path) = cache
        .file_path_to_id
        .iter()
        .find(|(_, id)| id.as_str() == module_id)
        .map(|(fp, _)| fp.clone())
    else {
        return (vec![], vec![]);
    };

    let file_name = Path::new(&file_path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();

    let mut child_nodes: Vec<GraphNode> = Vec::new();
    let mut added_ids: HashSet<String> = HashSet::new();

    for (ent_key, ent) in &cache.entities {
        if ent.file_path != file_path && ent.file_path != file_name {
            continue;
        }
        if ent.entity_type == "function" || ent.entity_type == "class" {
            child_nodes.push(GraphNode {
                id: ent_key.clone(),
                label: ent.name.clone(),
                node_type: ent.entity_type.clone(),
                metadata: NodeMetadata {
                    file_path: Some(file_path.clone()),
                    line_number: ent.line_number,
                    ..Default::default()
                },
                position: None,
            });
            added_ids.insert(ent_key.clone());
        }
    }

    let mut edges: Vec<GraphEdge> = Vec::new();
    for (ent_key, ent) in &cache.entities {
        if ent.file_path != file_path && ent.file_path != file_name {
            continue;
        }
        if ent.entity_type == "method" {
            if let Some(cn) = &ent.class_name {
                let class_key = format!("{}::{}", file_path, cn);
                if added_ids.contains(&class_key) {
                    let ek = &ent_key[..ent_key.len().min(8)];
                    let ck = &class_key[..class_key.len().min(8)];
                    edges.push(GraphEdge {
                        id: format!("e-{}-{}-meth", ek, ck),
                        source: ent_key.clone(),
                        target: class_key,
                        label: "has method".to_string(),
                        edge_type: "has_method".to_string(),
                    });
                }
            }
        }
    }

    (child_nodes, edges)
}

// ── Edge weights ────────────────────────────────────────────────────────────────

/// Weight for each relationship type. Lower = tighter coupling.
fn edge_weight(edge_type: &str) -> f64 {
    match edge_type {
        "calls" => 1.0,
        "has_method" => 1.0,
        "inherits_from" => 1.5,
        "imports_from" => 2.0,
        "imports_module" => 3.0,
        _ => 2.0,
    }
}

// ── Dijkstra path-finding ───────────────────────────────────────────────────────

#[derive(Clone)]
struct State {
    cost: f64,
    node: String,
}

impl PartialEq for State {
    fn eq(&self, other: &Self) -> bool {
        self.cost == other.cost
    }
}
impl Eq for State {}

impl PartialOrd for State {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for State {
    fn cmp(&self, other: &Self) -> Ordering {
        // Min-heap: reverse ordering so smallest cost pops first
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
    }
}

/// Result of a path query.
pub struct PathResult {
    pub found: bool,
    pub total_cost: f64,
    pub hops: usize,
    pub steps: Vec<PathStep>,
}

pub struct PathStep {
    pub node: String,
    pub label: String,
    pub file_path: Option<String>,
    pub edge_type: Option<String>,
    pub edge_cost: Option<f64>,
}

/// Look up human-readable info for a node ID from the graph cache.
fn node_info<'a>(id: &'a str, cache: &'a GraphCache) -> (&'a str, Option<&'a str>) {
    // Check nodes (docstore entries)
    for node in &cache.nodes {
        if node.id == id {
            return (node.label.as_str(), node.metadata.file_path.as_deref());
        }
    }
    // Check entities
    if let Some(ent) = cache.entities.get(id) {
        return (ent.name.as_str(), Some(ent.file_path.as_str()));
    }
    // External nodes: strip "external:" prefix for label
    if let Some(rest) = id.strip_prefix("external:") {
        let label = rest.split('.').last().unwrap_or(rest);
        return (label, None);
    }
    (id, None)
}

/// Find the shortest weighted path between two nodes using Dijkstra.
/// The graph is treated as undirected (edges traversable both ways).
pub fn find_path(source: &str, target: &str, cache: &GraphCache) -> PathResult {
    // Build adjacency list from edges (undirected), excluding external nodes
    let mut adj: HashMap<&str, Vec<(&str, &str, f64)>> = HashMap::new(); // node → [(neighbor, edge_type, weight)]
    for edge in &cache.edges {
        // Skip edges involving external (stdlib/third-party) nodes
        if edge.source.starts_with("external:") || edge.target.starts_with("external:") {
            continue;
        }
        let w = edge_weight(&edge.edge_type);
        adj.entry(edge.source.as_str()).or_default().push((
            edge.target.as_str(),
            edge.edge_type.as_str(),
            w,
        ));
        adj.entry(edge.target.as_str()).or_default().push((
            edge.source.as_str(),
            edge.edge_type.as_str(),
            w,
        ));
    }

    // Resolve source/target: try exact match, then suffix match, then entity resolution
    let resolve = |query: &str| -> Option<String> {
        // Exact match on node id
        if adj.contains_key(query) {
            return Some(query.to_string());
        }
        // Try file_path_to_id lookup (exact key)
        if let Some(id) = cache.file_path_to_id.get(query) {
            if adj.contains_key(id.as_str()) {
                return Some(id.clone());
            }
        }
        // Suffix match against file_path_to_id keys (handles relative vs absolute paths)
        for (fp, id) in &cache.file_path_to_id {
            if fp.ends_with(query) || query.ends_with(fp.as_str()) {
                if adj.contains_key(id.as_str()) {
                    return Some(id.clone());
                }
            }
        }
        // Suffix match against known node ids
        for key in adj.keys() {
            if key.ends_with(query) || query.ends_with(*key) {
                return Some(key.to_string());
            }
        }
        // Entity resolution: extract file path from entity key (e.g., "src/mimir/config.py::MimirConfig" → docstore ID)
        if query.contains("::") {
            let file_path = query.split("::").next().unwrap_or(query);
            // Try exact file path
            if let Some(id) = cache.file_path_to_id.get(file_path) {
                if adj.contains_key(id.as_str()) {
                    return Some(id.clone());
                }
            }
            // Try suffix match on the file path
            for (fp, id) in &cache.file_path_to_id {
                if fp.ends_with(file_path) || file_path.ends_with(fp.as_str()) {
                    if adj.contains_key(id.as_str()) {
                        return Some(id.clone());
                    }
                }
            }
            // Try the file path stem (without extension)
            let stem = Path::new(file_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or(file_path);
            for (fp, id) in &cache.file_path_to_id {
                let fp_path = Path::new(fp.as_str());
                let fp_stem = fp_path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                if fp.contains(stem) || stem.contains(&fp_stem) {
                    if adj.contains_key(id.as_str()) {
                        return Some(id.clone());
                    }
                }
            }
            // Try to find an entity: node that matches this entity key
            // Normalize: replace :: with . to convert entity format, but preserve file path slashes
            // Input: "src/mimir/config.py::MimirConfig"
            // Expected entity ID: "entity:src/mimir/config.py.MimirConfig"
            let normalized_query = query.replace("::", ".");
            let entity_id = format!("entity:{}", normalized_query);
            if adj.contains_key(entity_id.as_str()) {
                return Some(entity_id);
            }
            // For class-level queries (e.g., "src/mimir/config.py::MimirConfig"),
            // also try the file-level entity node as fallback
            if query.contains("::") {
                let file_path = query.split("::").next().unwrap_or(query);
                let file_entity = format!("entity:{}", file_path);
                if adj.contains_key(file_entity.as_str()) {
                    return Some(file_entity);
                }
            }
            // Check if query matches any edge source/target directly
            if adj.contains_key(&query) {
                return Some(query.to_string());
            }
            // Also check normalized edge sources/targets
            let normalized_query_dots = query.replace("::", ".").replace("/", ".");
            for key in adj.keys() {
                let normalized_key = key.replace("/", ".").replace("::", ".");
                if normalized_key == normalized_query_dots {
                    return Some(key.to_string());
                }
            }
        }
        None
    };

    let src = match resolve(source) {
        Some(s) => s,
        None => {
            return PathResult {
                found: false,
                total_cost: 0.0,
                hops: 0,
                steps: vec![],
            }
        }
    };
    let tgt = match resolve(target) {
        Some(t) => t,
        None => {
            return PathResult {
                found: false,
                total_cost: 0.0,
                hops: 0,
                steps: vec![],
            }
        }
    };

    if src == tgt {
        let (label, fp) = node_info(&src, cache);
        return PathResult {
            found: true,
            total_cost: 0.0,
            hops: 0,
            steps: vec![PathStep {
                node: src.clone(),
                label: label.to_string(),
                file_path: fp.map(|s| s.to_string()),
                edge_type: None,
                edge_cost: None,
            }],
        };
    }

    // Dijkstra
    let mut dist: HashMap<String, f64> = HashMap::new();
    let mut prev: HashMap<String, (String, String, f64)> = HashMap::new(); // node → (prev_node, edge_type, cost)
    let mut heap = BinaryHeap::new();

    dist.insert(src.clone(), 0.0);
    heap.push(State {
        cost: 0.0,
        node: src.clone(),
    });

    while let Some(State { cost, node }) = heap.pop() {
        if node == tgt {
            break;
        }
        // Skip stale entries
        if cost > *dist.get(&node).unwrap_or(&f64::INFINITY) {
            continue;
        }
        if let Some(neighbors) = adj.get(node.as_str()) {
            for &(neighbor, etype, w) in neighbors {
                let new_cost = cost + w;
                if new_cost < *dist.get(neighbor).unwrap_or(&f64::INFINITY) {
                    dist.insert(neighbor.to_string(), new_cost);
                    prev.insert(neighbor.to_string(), (node.clone(), etype.to_string(), w));
                    heap.push(State {
                        cost: new_cost,
                        node: neighbor.to_string(),
                    });
                }
            }
        }
    }

    // Reconstruct path
    if !prev.contains_key(&tgt) && src != tgt {
        return PathResult {
            found: false,
            total_cost: 0.0,
            hops: 0,
            steps: vec![],
        };
    }

    let mut steps = Vec::new();
    let mut current = tgt.clone();
    let (label, fp) = node_info(&current, cache);
    steps.push(PathStep {
        node: current.clone(),
        label: label.to_string(),
        file_path: fp.map(|s| s.to_string()),
        edge_type: None,
        edge_cost: None,
    });

    while let Some((prev_node, etype, cost)) = prev.get(&current) {
        let (label, fp) = node_info(prev_node, cache);
        steps.push(PathStep {
            node: prev_node.clone(),
            label: label.to_string(),
            file_path: fp.map(|s| s.to_string()),
            edge_type: Some(etype.clone()),
            edge_cost: Some(*cost),
        });
        current = prev_node.clone();
    }
    steps.reverse();

    let total_cost = *dist.get(&tgt).unwrap_or(&0.0);

    PathResult {
        found: true,
        total_cost,
        hops: steps.len() - 1,
        steps,
    }
}

// ── Neighbor search ─────────────────────────────────────────────────────────────

pub struct NeighborResult {
    pub center: String,
    pub neighbors: Vec<NeighborEntry>,
}

pub struct NeighborEntry {
    pub node: String,
    pub label: String,
    pub file_path: Option<String>,
    pub edge_type: String,
    pub direction: String, // "outgoing" or "incoming"
}

/// Find neighbors of a node up to `depth` hops away.
/// Optionally filter by relationship type.
pub fn find_neighbors(
    node_id: &str,
    depth: usize,
    relation_type: Option<&str>,
    cache: &GraphCache,
) -> NeighborResult {
    let depth = depth.clamp(1, 5);

    // Resolve node
    let resolve = |query: &str| -> Option<String> {
        // Check if it's a known node id (from edges or entities)
        for edge in &cache.edges {
            if edge.source == query || edge.target == query {
                return Some(query.to_string());
            }
        }
        if cache.entities.contains_key(query) {
            // Entity keys in relationships use :: format (e.g., "src/mimir/config.py::MimirConfig")
            // But edges use entity: prefix with :: replaced by . (e.g., "entity:src/mimir/config.py.MimirConfig")
            let entity_id = format!("entity:{}", query.replace("::", "."));
            return Some(entity_id);
        }
        // Check for entity: prefix (internal entity nodes created during graph build)
        if query.starts_with("entity:") && cache.edges.iter().any(|e| e.source == query || e.target == query) {
            return Some(query.to_string());
        }
        // File path lookup (exact)
        if let Some(id) = cache.file_path_to_id.get(query) {
            return Some(id.clone());
        }
        // Suffix match against file_path_to_id keys (relative vs absolute)
        for (fp, id) in &cache.file_path_to_id {
            if fp.ends_with(query) || query.ends_with(fp.as_str()) {
                return Some(id.clone());
            }
        }
        // Suffix match against edges
        for edge in &cache.edges {
            if edge.source.ends_with(query) {
                return Some(edge.source.clone());
            }
            if edge.target.ends_with(query) {
                return Some(edge.target.clone());
            }
        }
        // Entity resolution: extract file path from entity key (e.g., "src/mimir/config.py::MimirConfig" → "src/mimir/config.py")
        if query.contains("::") {
            let file_path = query.split("::").next().unwrap_or(query);
            // Try exact file path
            if let Some(id) = cache.file_path_to_id.get(file_path) {
                return Some(id.clone());
            }
            // Try suffix match on the file path
            for (fp, id) in &cache.file_path_to_id {
                if fp.ends_with(file_path) || file_path.ends_with(fp.as_str()) {
                    return Some(id.clone());
                }
            }
            // Try the file path stem (without extension)
            let stem = Path::new(file_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or(file_path);
            for (fp, id) in &cache.file_path_to_id {
                let fp_path = Path::new(fp.as_str());
                let fp_stem = fp_path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                if fp.contains(stem) || stem.contains(&fp_stem) {
                    return Some(id.clone());
                }
            }
            // Try to find an entity: node that matches this entity key
            // Normalize: replace :: with . to convert entity format, but preserve file path slashes
            // Input: "src/mimir/config.py::MimirConfig"
            // Expected entity ID: "entity:src/mimir/config.py.MimirConfig"
            let normalized_query = query.replace("::", ".");
            let entity_id = format!("entity:{}", normalized_query);
            if cache.edges.iter().any(|e| e.source == entity_id || e.target == entity_id) {
                return Some(entity_id);
            }
            // Try with file path format (entity:src/mimir/config.py) - keep slashes
            if query.contains("::") {
                let entity_id_fp = format!("entity:{}", query.split("::").next().unwrap_or(query));
                if cache.edges.iter().any(|e| e.source == entity_id_fp || e.target == entity_id_fp) {
                    return Some(entity_id_fp);
                }
                // For class-level queries (e.g., "src/mimir/config.py::MimirConfig"),
                // fall back to the file-level entity node (entity:src/mimir/config.py)
                // This allows traversing the file's connections
                let file_path = query.split("::").next().unwrap_or(query);
                let file_entity = format!("entity:{}", file_path);
                if cache.edges.iter().any(|e| e.source == file_entity || e.target == file_entity) {
                    return Some(file_entity);
                }
            }
            // Check if query matches any edge source/target and return it directly
            for edge in &cache.edges {
                // Direct match first
                if edge.source == query {
                    return Some(edge.source.clone());
                }
                if edge.target == query {
                    return Some(edge.target.clone());
                }
                // Try prefix match - for class queries, match file paths
                if query.contains("::") {
                    let prefix = query.split("::").next().unwrap_or("");
                    // Normalize prefix to dots for matching entity:src.mimir.config.MimirConfig style
                    let normalized_prefix = prefix.replace("/", ".");
                    // Check if edge source starts with either original or normalized prefix
                    if edge.source.starts_with(prefix) || edge.source.replace("/", ".").starts_with(&normalized_prefix) {
                        return Some(edge.source.clone());
                    }
                }
            }
            // Also check normalized forms as fallback
            let normalized_query = query.replace("::", ".").replace("/", ".");
            for edge in &cache.edges {
                let normalized_src = edge.source.replace("/", ".").replace("::", ".");
                let normalized_tgt = edge.target.replace("/", ".").replace("::", ".");
                if normalized_src == normalized_query {
                    return Some(edge.source.clone());
                }
                if normalized_tgt == normalized_query {
                    return Some(edge.target.clone());
                }
            }
        }
        None
    };

    let center = match resolve(node_id) {
        Some(n) => n,
        None => {
            return NeighborResult {
                center: node_id.to_string(),
                neighbors: vec![],
            }
        }
    };

    let matches_type = |etype: &str| -> bool {
        match relation_type {
            Some(filter) => etype == filter,
            None => true,
        }
    };

    let mut visited: HashSet<String> = HashSet::new();
    visited.insert(center.clone());
    let mut frontier = vec![center.clone()];
    let mut all_neighbors: Vec<NeighborEntry> = Vec::new();

    for _ in 0..depth {
        let mut next_frontier = Vec::new();
        for current in &frontier {
            // Normalize current for edge matching
            let current_normalized = current.replace("/", ".").replace("::", ".");
            // Strip entity: prefix for raw version
            let current_raw = if current.starts_with("entity:") {
                current[7..].to_string()
            } else {
                current.clone()
            };
            for edge in &cache.edges {
                // Strip entity: prefix from edge sources/targets for comparison
                let edge_src_stripped = if edge.source.starts_with("entity:") {
                    &edge.source[7..]
                } else {
                    &edge.source[..]
                };
                let edge_tgt_stripped = if edge.target.starts_with("entity:") {
                    &edge.target[7..]
                } else {
                    &edge.target[..]
                };
                // Normalize stripped versions
                let edge_src_norm = edge_src_stripped.replace("/", ".").replace("::", ".");
                let edge_tgt_norm = edge_tgt_stripped.replace("/", ".").replace("::", ".");
                
                // Outgoing: current → target
                // Check if edge.source matches current (any format)
                let src_matches = edge.source == *current 
                    || edge_src_norm == current_normalized
                    || edge_src_stripped == current_raw
                    || edge_src_norm == current_raw.replace("/", ".");
                if src_matches && !visited.contains(&edge.target) {
                    if matches_type(&edge.edge_type) {
                        let (label, fp) = node_info(&edge.target, cache);
                        all_neighbors.push(NeighborEntry {
                            node: edge.target.clone(),
                            label: label.to_string(),
                            file_path: fp.map(|s| s.to_string()),
                            edge_type: edge.edge_type.clone(),
                            direction: "outgoing".to_string(),
                        });
                    }
                    visited.insert(edge.target.clone());
                    next_frontier.push(edge.target.clone());
                }
                // Incoming: source → current
                // Check if edge.target matches current (any format)
                let tgt_matches = edge.target == *current
                    || edge_tgt_norm == current_normalized
                    || edge_tgt_stripped == current_raw
                    || edge_tgt_norm == current_raw.replace("/", ".");
                if tgt_matches && !visited.contains(&edge.source) {
                    if matches_type(&edge.edge_type) {
                        let (label, fp) = node_info(&edge.source, cache);
                        all_neighbors.push(NeighborEntry {
                            node: edge.source.clone(),
                            label: label.to_string(),
                            file_path: fp.map(|s| s.to_string()),
                            edge_type: edge.edge_type.clone(),
                            direction: "incoming".to_string(),
                        });
                    }
                    visited.insert(edge.source.clone());
                    next_frontier.push(edge.source.clone());
                }
            }
        }
        frontier = next_frontier;
        if frontier.is_empty() {
            break;
        }
    }

    NeighborResult {
        center,
        neighbors: all_neighbors,
    }
}

// ── Graph statistics ─────────────────────────────────────────────────────────────

pub struct GraphStats {
    pub total_nodes: usize,
    pub total_edges: usize,
    pub total_entities: usize,
    pub by_relation_type: HashMap<String, usize>,
    pub by_language: HashMap<String, usize>,
    pub top_connected: Vec<(String, u32)>,
}

/// Compute summary statistics about the knowledge graph.
pub fn compute_stats(cache: &GraphCache) -> GraphStats {
    let mut by_type: HashMap<String, usize> = HashMap::new();
    let mut by_lang: HashMap<String, usize> = HashMap::new();

    for edge in &cache.edges {
        *by_type.entry(edge.edge_type.clone()).or_insert(0) += 1;
    }

    for ent in cache.entities.values() {
        let lang = match ent.file_path.rsplit('.').next() {
            Some("py") => "python",
            Some("ts") | Some("tsx") => "typescript",
            Some("js") | Some("jsx") => "javascript",
            Some("rs") => "rust",
            Some("go") => "go",
            _ => "other",
        };
        *by_lang.entry(lang.to_string()).or_insert(0) += 1;
    }

    // Top 10 most connected nodes
    let mut degree_vec: Vec<(String, u32)> =
        cache.degree.iter().map(|(k, v)| (k.clone(), *v)).collect();
    degree_vec.sort_by(|a, b| b.1.cmp(&a.1));
    degree_vec.truncate(10);

    GraphStats {
        total_nodes: cache.nodes.len(),
        total_edges: cache.edges.len(),
        total_entities: cache.entities.len(),
        by_relation_type: by_type,
        by_language: by_lang,
        top_connected: degree_vec,
    }
}

// ── Force-directed layout ──────────────────────────────────────────────────────

/// Spatial hash grid for O(n) approximate repulsion.
/// Nodes are bucketed into cells; repulsion is only computed between
/// nodes in the same or adjacent cells.  Distant cells are skipped
/// because their contribution is negligible at that distance.
struct SpatialGrid {
    cell_size: f64,
    cells: HashMap<(i64, i64), Vec<usize>>,
}

impl SpatialGrid {
    fn new(cell_size: f64) -> Self {
        Self {
            cell_size,
            cells: HashMap::new(),
        }
    }

    fn clear(&mut self) {
        self.cells.clear();
    }

    fn insert(&mut self, x: f64, y: f64, idx: usize) {
        let key = (
            (x / self.cell_size).floor() as i64,
            (y / self.cell_size).floor() as i64,
        );
        self.cells.entry(key).or_default().push(idx);
    }

    /// Returns indices of nodes in the same cell and all 8 neighbors.
    fn neighbors(&self, x: f64, y: f64) -> Vec<usize> {
        let cx = (x / self.cell_size).floor() as i64;
        let cy = (y / self.cell_size).floor() as i64;
        let mut result = Vec::new();
        for dx in -1..=1 {
            for dy in -1..=1 {
                if let Some(bucket) = self.cells.get(&(cx + dx, cy + dy)) {
                    result.extend_from_slice(bucket);
                }
            }
        }
        result
    }
}

/// Pre-compute node positions using a force-directed layout algorithm.
/// Uses a spatial hash grid so repulsion is O(n) instead of O(n²).
pub fn compute_layout(nodes: &[GraphNode], edges: &[GraphEdge]) -> HashMap<String, (f64, f64)> {
    let n = nodes.len();
    if n == 0 {
        return HashMap::new();
    }
    if n == 1 {
        let mut pos = HashMap::new();
        pos.insert(nodes[0].id.clone(), (0.0, 0.0));
        return pos;
    }

    let t_start = std::time::Instant::now();

    // ── Parameters ─────────────────────────────────────────────────────────
    let iterations: usize = 200;
    let repulsion_strength: f64 = 8000.0;
    let ideal_edge_length: f64 = 100.0;
    let edge_elasticity: f64 = 0.45;
    let gravity: f64 = 0.1;
    let cooling_factor: f64 = 0.95;
    let initial_temp: f64 = 200.0;
    let min_temp: f64 = 1.0;
    let padding: f64 = 50.0;
    // Grid cell size — nodes farther than this contribute negligible force
    let cell_size = (repulsion_strength * 4.0).sqrt();

    // ── Build adjacency list ───────────────────────────────────────────────
    let id_to_idx: HashMap<&str, usize> = nodes
        .iter()
        .enumerate()
        .map(|(i, node)| (node.id.as_str(), i))
        .collect();

    let mut adj: Vec<Vec<usize>> = vec![Vec::new(); n];
    for edge in edges {
        if let (Some(&si), Some(&ti)) = (
            id_to_idx.get(edge.source.as_str()),
            id_to_idx.get(edge.target.as_str()),
        ) {
            adj[si].push(ti);
            adj[ti].push(si);
        }
    }

    // ── Initialize positions in a circle ───────────────────────────────────
    let radius = (n as f64).sqrt() * ideal_edge_length;
    let mut px = vec![0.0f64; n];
    let mut py = vec![0.0f64; n];
    for i in 0..n {
        let angle = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
        px[i] = radius * angle.cos();
        py[i] = radius * angle.sin();
    }

    let mut vx = vec![0.0f64; n];
    let mut vy = vec![0.0f64; n];
    let mut temp = initial_temp;
    let mut grid = SpatialGrid::new(cell_size);

    // ── Main simulation loop ───────────────────────────────────────────────
    for _iter in 0..iterations {
        vx.fill(0.0);
        vy.fill(0.0);

        // Rebuild spatial grid
        grid.clear();
        for i in 0..n {
            grid.insert(px[i], py[i], i);
        }

        // ── Repulsion (nearby pairs only via spatial grid) ─────────────────
        for i in 0..n {
            let neighbors = grid.neighbors(px[i], py[i]);
            for &j in &neighbors {
                if j <= i {
                    continue;
                }
                let dx = px[i] - px[j];
                let dy = py[i] - py[j];
                let dist_sq = dx * dx + dy * dy;
                let dist = dist_sq.sqrt().max(1.0);

                let force = repulsion_strength / dist_sq;
                let fx = (dx / dist) * force;
                let fy = (dy / dist) * force;

                vx[i] += fx;
                vy[i] += fy;
                vx[j] -= fx;
                vy[j] -= fy;
            }
        }

        // ── Attraction (edges) ─────────────────────────────────────────────
        for i in 0..n {
            for &j in &adj[i] {
                if j <= i {
                    continue;
                }
                let dx = px[j] - px[i];
                let dy = py[j] - py[i];
                let dist = (dx * dx + dy * dy).sqrt().max(1.0);

                let displacement = dist - ideal_edge_length;
                let force = edge_elasticity * displacement;
                let fx = (dx / dist) * force;
                let fy = (dy / dist) * force;

                vx[i] += fx;
                vy[i] += fy;
                vx[j] -= fx;
                vy[j] -= fy;
            }
        }

        // ── Gravity (pull toward center) ───────────────────────────────────
        for i in 0..n {
            let dist = (px[i] * px[i] + py[i] * py[i]).sqrt().max(1.0);
            vx[i] -= gravity * px[i] / dist;
            vy[i] -= gravity * py[i] / dist;
        }

        // ── Apply forces with temperature cap ──────────────────────────────
        let mut total_movement = 0.0f64;
        for i in 0..n {
            let speed = (vx[i] * vx[i] + vy[i] * vy[i]).sqrt();
            if speed > temp {
                let scale = temp / speed;
                vx[i] *= scale;
                vy[i] *= scale;
            }
            px[i] += vx[i];
            py[i] += vy[i];
            total_movement += vx[i].abs() + vy[i].abs();
        }

        temp = (temp * cooling_factor).max(min_temp);

        // Early stopping: if total movement is negligible, converged
        if total_movement < (n as f64) * 0.01 {
            tracing::info!(
                "layout converged at iteration {} (total_movement={:.2})",
                _iter,
                total_movement
            );
            break;
        }
    }

    // ── Normalize to positive coordinates with padding ─────────────────────
    let min_x = px.iter().copied().fold(f64::INFINITY, f64::min);
    let min_y = py.iter().copied().fold(f64::INFINITY, f64::min);

    let mut positions = HashMap::with_capacity(n);
    for i in 0..n {
        positions.insert(
            nodes[i].id.clone(),
            (px[i] - min_x + padding, py[i] - min_y + padding),
        );
    }

    let elapsed = t_start.elapsed();
    tracing::info!(
        "compute_layout: {} nodes, {} edges, completed in {:.1?}",
        n,
        edges.len(),
        elapsed
    );

    positions
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn is_code_file(name: &str) -> bool {
    matches!(
        Path::new(name)
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or(""),
        "py" | "ts" | "tsx" | "js" | "jsx" | "rs" | "go"
    )
}

type SuffixIndex = HashMap<String, Vec<(String, String)>>; // suffix → [(file_path, node_id)]

fn build_suffix_index(fp_to_id: &HashMap<String, String>) -> SuffixIndex {
    let mut idx: SuffixIndex = HashMap::new();
    for (fp, id) in fp_to_id {
        let parts: Vec<&str> = Path::new(fp)
            .components()
            .filter_map(|c| c.as_os_str().to_str())
            .collect();
        for i in 0..parts.len() {
            let suffix = parts[i..].join("/");
            idx.entry(suffix)
                .or_default()
                .push((fp.clone(), id.clone()));
        }
    }
    idx
}

fn lookup_suffix(target: &str, idx: &SuffixIndex) -> Option<String> {
    let stem = Path::new(target)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    let base = Path::new(target)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    let ext = Path::new(target)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");

    // Build candidates based on the actual file extension
    let mut candidates: Vec<String> = vec![target.to_string(), base.to_string(), stem.to_string()];

    // Add extension-specific patterns
    if ext == "py" || ext.is_empty() {
        candidates.push(format!("{}.py", target));
        candidates.push(format!("{}.py", target.replace('.', "/")));
        candidates.push(format!("{}.py", stem));
    }
    if ext == "rs" || ext.is_empty() {
        candidates.push(format!("{}.rs", target));
        candidates.push(format!("{}.rs", stem));
    }

    for key in &candidates {
        if let Some(matches) = idx.get(key.as_str()) {
            if let Some((_, id)) = matches.first() {
                return Some(id.clone());
            }
        }
    }
    None
}
