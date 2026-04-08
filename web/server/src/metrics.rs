use anyhow::Result;
use chrono::{Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

// ── Constants ──────────────────────────────────────────────────────────────────

/// Traditional token estimates per query type (no context optimization).
/// Matches the TypeScript TRADITIONAL_TOKENS in types/metrics.ts.
const TRADITIONAL_TOKENS: &[(&str, u64)] = &[
    ("search", 3000),
    ("query", 8000),
    ("rag", 12000),
    ("agent", 15000),
];

/// Cost per 1k tokens for traditional approach (no caching, full context).
const TRADITIONAL_COST_PER_1K: f64 = 0.001;

/// Estimated time per traditional query (seconds) — manual search + read.
const TRADITIONAL_TIME_SECS: f64 = 30.0;

/// Estimated time per Mimir query (seconds) — automated retrieval.
const MIMIR_TIME_SECS: f64 = 2.0;

fn traditional_tokens_for(query_type: &str) -> u64 {
    TRADITIONAL_TOKENS
        .iter()
        .find(|(t, _)| *t == query_type)
        .map(|(_, v)| *v)
        .unwrap_or(5000)
}

fn traditional_cost_for(query_type: &str, count: u64) -> f64 {
    (traditional_tokens_for(query_type) as f64 / 1000.0) * TRADITIONAL_COST_PER_1K * count as f64
}

// ── Raw JSONL entry ───────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct MetricEntry {
    timestamp: String,
    query_type: String,
    #[allow(dead_code)]
    #[serde(default)]
    model: String,
    #[serde(default)]
    tokens_in: u64,
    #[serde(default)]
    tokens_out: u64,
    #[serde(default)]
    cost: f64,
    #[serde(default)]
    docs_retrieved: u32,
    #[serde(default)]
    duration_ms: u64,
    #[serde(default)]
    embedding_cost: f64,
    #[serde(default)]
    llm_input_cost: f64,
    #[serde(default)]
    llm_output_cost: f64,
}

// ── Response types ────────────────────────────────────────────────────────────

#[derive(Serialize, Default, Clone)]
pub struct TypeSummary {
    pub count: u64,
    pub total_cost: f64,
    pub avg_cost: f64,
    pub total_tokens_in: u64,
    pub total_tokens_out: u64,
    pub avg_duration_ms: f64,
    pub avg_docs_retrieved: f64,
}

#[derive(Serialize)]
pub struct Summary {
    pub total_queries: u64,
    pub total_cost: f64,
    pub avg_cost_per_query: f64,
    pub total_tokens_in: u64,
    pub total_tokens_out: u64,
    pub traditional_cost: f64,
    pub savings: f64,
    pub savings_percent: f64,
    pub time_saved_secs: f64,
    pub by_type: HashMap<String, TypeSummary>,
}

#[derive(Serialize)]
pub struct DailyEntry {
    pub date: String,
    pub queries: u64,
    pub cost: f64,
    pub traditional_cost: f64,
    pub tokens_in: u64,
    pub tokens_out: u64,
}

#[derive(Serialize)]
pub struct BreakdownEntry {
    pub query_type: String,
    pub count: u64,
    pub cost: f64,
    pub avg_cost: f64,
    pub embedding_cost: f64,
    pub llm_input_cost: f64,
    pub llm_output_cost: f64,
    pub traditional_cost: f64,
    pub savings: f64,
}

#[derive(Serialize, Default)]
pub struct ComponentTotals {
    pub embedding_cost: f64,
    pub llm_input_cost: f64,
    pub llm_output_cost: f64,
    pub total_cost: f64,
    pub count: u64,
}

// ── Loader ────────────────────────────────────────────────────────────────────

fn load_entries(project_root: &Path, days: u32) -> Result<Vec<MetricEntry>> {
    let path = project_root.join(".knowledge").join("cost_metrics.jsonl");
    if !path.exists() {
        return Ok(vec![]);
    }

    let cutoff = (Utc::now() - Duration::days(days as i64))
        .format("%Y-%m-%dT%H:%M:%S")
        .to_string();

    let content = std::fs::read_to_string(&path)?;
    let entries = content
        .lines()
        .filter(|l| !l.trim().is_empty())
        .filter_map(|l| serde_json::from_str::<MetricEntry>(l).ok())
        // ISO 8601 without TZ sorts lexicographically — slice to 19 chars for safe compare
        .filter(|e| e.timestamp.get(..19).unwrap_or("") >= cutoff.get(..19).unwrap_or(""))
        .collect();

    Ok(entries)
}

// ── Public API ────────────────────────────────────────────────────────────────

pub fn get_summary(project_root: &Path, days: u32) -> Result<Summary> {
    let entries = load_entries(project_root, days)?;
    let mut by_type: HashMap<String, TypeSummary> = HashMap::new();

    for e in &entries {
        let t = by_type.entry(e.query_type.clone()).or_default();
        t.count += 1;
        t.total_cost += e.cost;
        t.total_tokens_in += e.tokens_in;
        t.total_tokens_out += e.tokens_out;
        t.avg_duration_ms += e.duration_ms as f64;
        t.avg_docs_retrieved += e.docs_retrieved as f64;
    }

    for t in by_type.values_mut() {
        if t.count > 0 {
            t.avg_cost = t.total_cost / t.count as f64;
            t.avg_duration_ms /= t.count as f64;
            t.avg_docs_retrieved /= t.count as f64;
        }
    }

    let total_queries = entries.len() as u64;
    let total_cost: f64 = entries.iter().map(|e| e.cost).sum();
    let total_tokens_in: u64 = entries.iter().map(|e| e.tokens_in).sum();
    let total_tokens_out: u64 = entries.iter().map(|e| e.tokens_out).sum();

    // Calculate traditional cost (what it would cost without Mimir's optimization)
    let traditional_cost: f64 = by_type
        .iter()
        .map(|(qt, summary)| traditional_cost_for(qt, summary.count))
        .sum();

    let savings = traditional_cost - total_cost;
    let savings_percent = if traditional_cost > 0.0 {
        (savings / traditional_cost) * 100.0
    } else {
        0.0
    };

    // Time saved: traditional approach takes ~30s per query, Mimir takes ~2s
    let time_saved_secs = total_queries as f64 * (TRADITIONAL_TIME_SECS - MIMIR_TIME_SECS);

    Ok(Summary {
        total_queries,
        total_cost,
        avg_cost_per_query: if total_queries > 0 {
            total_cost / total_queries as f64
        } else {
            0.0
        },
        total_tokens_in,
        total_tokens_out,
        traditional_cost,
        savings,
        savings_percent,
        time_saved_secs,
        by_type,
    })
}

pub fn get_daily(project_root: &Path, days: u32) -> Result<Vec<DailyEntry>> {
    let entries = load_entries(project_root, days)?;
    let mut by_date: HashMap<String, (u64, f64, u64, u64, HashMap<String, u64>)> = HashMap::new();

    for e in &entries {
        let date = e.timestamp.get(..10).unwrap_or("unknown").to_string();
        let entry = by_date
            .entry(date.clone())
            .or_insert((0u64, 0.0, 0u64, 0u64, HashMap::new()));
        entry.0 += 1; // count
        entry.1 += e.cost; // cost
        entry.2 += e.tokens_in; // tokens_in
        entry.3 += e.tokens_out; // tokens_out
        *entry.4.entry(e.query_type.clone()).or_insert(0) += 1; // count by type
    }

    let mut daily: Vec<DailyEntry> = by_date
        .into_iter()
        .map(
            |(date, (count, cost, tokens_in, tokens_out, type_counts))| {
                let traditional_cost: f64 = type_counts
                    .iter()
                    .map(|(qt, cnt)| traditional_cost_for(qt, *cnt))
                    .sum();
                DailyEntry {
                    date,
                    queries: count,
                    cost,
                    traditional_cost,
                    tokens_in,
                    tokens_out,
                }
            },
        )
        .collect();
    daily.sort_by(|a, b| a.date.cmp(&b.date));
    Ok(daily)
}

pub fn get_breakdown(project_root: &Path, days: u32) -> Result<Vec<BreakdownEntry>> {
    let entries = load_entries(project_root, days)?;
    let mut by_type: HashMap<String, (u64, f64, f64, f64, f64)> = HashMap::new();

    for e in &entries {
        let entry = by_type
            .entry(e.query_type.clone())
            .or_insert((0u64, 0.0, 0.0, 0.0, 0.0));
        entry.0 += 1; // count
        entry.1 += e.cost; // total_cost
        entry.2 += e.embedding_cost; // embedding_cost
        entry.3 += e.llm_input_cost; // llm_input_cost
        entry.4 += e.llm_output_cost; // llm_output_cost
    }

    let breakdown: Vec<BreakdownEntry> = by_type
        .into_iter()
        .map(|(qt, (count, cost, embedding, llm_in, llm_out))| {
            let traditional = traditional_cost_for(&qt, count);
            BreakdownEntry {
                query_type: qt.clone(),
                count,
                cost,
                avg_cost: if count > 0 { cost / count as f64 } else { 0.0 },
                embedding_cost: embedding,
                llm_input_cost: llm_in,
                llm_output_cost: llm_out,
                traditional_cost: traditional,
                savings: traditional - cost,
            }
        })
        .collect();

    Ok(breakdown)
}

pub fn get_components(project_root: &Path, days: u32) -> Result<ComponentTotals> {
    let entries = load_entries(project_root, days)?;
    let mut totals = ComponentTotals::default();

    for e in &entries {
        totals.embedding_cost += e.embedding_cost;
        totals.llm_input_cost += e.llm_input_cost;
        totals.llm_output_cost += e.llm_output_cost;
        totals.total_cost += e.cost;
        totals.count += 1;
    }

    Ok(totals)
}
