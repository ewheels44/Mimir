use anyhow::{Context, Result};
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
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
        let Some(source_id) = lookup_suffix(&rel.source, &suffix_idx) else {
            continue;
        };

        let target_id = match lookup_suffix(&rel.target, &suffix_idx) {
            Some(id) => id,
            None => {
                // External module not in the index

                let ext_id = format!("external:{}", rel.target);
                if !existing_ids.contains(&ext_id) && ext_ids.insert(ext_id.clone()) {
                    let ext_label = if rel.target.contains('/') || rel.target.contains('\\') {
                        Path::new(&rel.target)
                            .file_name()
                            .map(|n| n.to_string_lossy().to_string())
                            .unwrap_or_else(|| rel.target.clone())
                    } else {
                        rel.target
                            .split('.')
                            .last()
                            .unwrap_or(&rel.target)
                            .to_string()
                    };
                    ext_nodes.push(GraphNode {
                        id: ext_id.clone(),
                        label: ext_label,
                        node_type: "module".to_string(),
                        metadata: NodeMetadata {
                            module_path: Some(rel.target.clone()),
                            external: Some(true),
                            ..Default::default()
                        },
                        position: None,
                    });
                }
                ext_id
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
