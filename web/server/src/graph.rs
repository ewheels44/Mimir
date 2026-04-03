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

    Ok(GraphCache {
        cache_key: key,
        nodes,
        edges,
        degree,
        file_path_to_id,
        entities,
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
