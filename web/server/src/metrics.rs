use anyhow::Result;
use chrono::{Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

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
    pub by_type: HashMap<String, TypeSummary>,
}

#[derive(Serialize)]
pub struct DailyEntry {
    pub date: String,
    pub count: u64,
    pub cost: f64,
    pub tokens_in: u64,
    pub tokens_out: u64,
}

#[derive(Serialize)]
pub struct BreakdownEntry {
    pub query_type: String,
    #[serde(flatten)]
    pub stats: TypeSummary,
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
        by_type,
    })
}

pub fn get_daily(project_root: &Path, days: u32) -> Result<Vec<DailyEntry>> {
    let entries = load_entries(project_root, days)?;
    let mut by_date: HashMap<String, DailyEntry> = HashMap::new();

    for e in &entries {
        let date = e.timestamp.get(..10).unwrap_or("unknown").to_string();
        let day = by_date.entry(date.clone()).or_insert(DailyEntry {
            date,
            count: 0,
            cost: 0.0,
            tokens_in: 0,
            tokens_out: 0,
        });
        day.count += 1;
        day.cost += e.cost;
        day.tokens_in += e.tokens_in;
        day.tokens_out += e.tokens_out;
    }

    let mut daily: Vec<DailyEntry> = by_date.into_values().collect();
    daily.sort_by(|a, b| a.date.cmp(&b.date));
    Ok(daily)
}

pub fn get_breakdown(project_root: &Path, days: u32) -> Result<Vec<BreakdownEntry>> {
    let summary = get_summary(project_root, days)?;
    Ok(summary
        .by_type
        .into_iter()
        .map(|(qt, stats)| BreakdownEntry {
            query_type: qt,
            stats,
        })
        .collect())
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
