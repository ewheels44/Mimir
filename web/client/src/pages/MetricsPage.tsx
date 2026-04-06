import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  TooltipItem,
} from 'chart.js';
import { Doughnut, Bar, Line } from 'react-chartjs-2';

import {
  MetricsSummary,
  DailyMetrics,
  QueryBreakdown,
  ComponentCosts,
  TRADITIONAL_TOKENS,
} from '../types/metrics';

import styles from './MetricsPage.module.css';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

// Chart.js defaults
ChartJS.defaults.color = '#94a3b8';
ChartJS.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
ChartJS.defaults.plugins.tooltip.backgroundColor = '#1e293b';
ChartJS.defaults.plugins.tooltip.titleColor = '#f8fafc';
ChartJS.defaults.plugins.tooltip.bodyColor = '#f8fafc';
ChartJS.defaults.plugins.tooltip.borderColor = '#334155';
ChartJS.defaults.plugins.tooltip.borderWidth = 1;
ChartJS.defaults.plugins.tooltip.padding = 10;
ChartJS.defaults.plugins.tooltip.cornerRadius = 6;

// Color palette
const COLORS = {
  blue: '#378ADD',
  teal: '#1D9E75',
  amber: '#EF9F27',
  coral: '#D85A30',
  gray: '#888780',
  purple: '#7F77DD',
  blueFade: 'rgba(55,138,221,0.18)',
  grayFade: 'rgba(136,135,128,0.12)',
};

// Formatters
const fmt$ = (v: number) => '$' + Math.abs(v).toFixed(v >= 0.01 ? 3 : 5);
const fmtN = (v: number) => v.toLocaleString();

// Default empty data
const DEFAULT_SUMMARY: MetricsSummary = {
  total_queries: 0,
  total_cost: 0,
  traditional_cost: 0,
  savings: 0,
  savings_percent: 0,
  by_type: {},
};

const DEFAULT_COMPONENTS: ComponentCosts = {
  embedding_cost: 0,
  llm_input_cost: 0,
  llm_output_cost: 0,
  total_cost: 0,
};

// ── Custom Hooks ─────────────────────────────────────────────────────────────

function useMetricsData(days: number) {
  const [summary, setSummary] = useState<MetricsSummary>(DEFAULT_SUMMARY);
  const [daily, setDaily] = useState<DailyMetrics[]>([]);
  const [breakdown, setBreakdown] = useState<QueryBreakdown[]>([]);
  const [components, setComponents] = useState<ComponentCosts>(DEFAULT_COMPONENTS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      fetch(`/api/metrics/summary?days=${days}`).then(r => r.ok ? r.json() : null),
      fetch(`/api/metrics/daily?days=${days}`).then(r => r.ok ? r.json() : null),
      fetch(`/api/metrics/breakdown?days=${days}`).then(r => r.ok ? r.json() : null),
      fetch(`/api/metrics/components?days=${days}`).then(r => r.ok ? r.json() : null),
    ]).then(([s, d, b, c]) => {
      setSummary(s.status === 'fulfilled' && s.value ? s.value : DEFAULT_SUMMARY);
      setDaily(d.status === 'fulfilled' && d.value ? d.value : []);
      setBreakdown(b.status === 'fulfilled' && b.value ? b.value : []);
      setComponents(c.status === 'fulfilled' && c.value ? c.value : DEFAULT_COMPONENTS);
      setLoading(false);
    });
  }, [days]);

  return { summary, daily, breakdown, components, loading };
}

// ── Summary Cards ─────────────────────────────────────────────────────────────

interface SummaryCardsProps {
  summary: MetricsSummary;
}

function SummaryCards({ summary }: SummaryCardsProps) {
  const BUDGET = 10.0;
  const spent = summary.total_cost || 0;
  const pct = Math.min(100, (spent / BUDGET) * 100);
  const barColor = pct > 80 ? 'var(--red)' : pct > 50 ? 'var(--amber)' : 'var(--accent-light)';

  return (
    <div className={styles.cards}>
      <div className={styles.mcard} data-highlight>
        <div className={styles.mcardLabel}>Amount Spent</div>
        <div className={styles.mcardVal}>{fmt$(summary.total_cost || 0)}</div>
        <div className={styles.mcardSub}>actual API cost</div>
        <div className={styles.progressTrack}>
          <div
            className={styles.progressBar}
            style={{ width: `${pct}%`, background: barColor }}
          />
        </div>
        <div className={styles.mcardSub}>
          {pct.toFixed(1)}% of ${BUDGET.toFixed(0)} typical budget
        </div>
      </div>

      <div className={styles.mcard}>
        <div className={styles.mcardLabel}>Total queries</div>
        <div className={styles.mcardVal}>{fmtN(summary.total_queries || 0)}</div>
        <div className={styles.mcardSub}>in period</div>
      </div>

      <div className={styles.mcard}>
        <div className={styles.mcardLabel}>Without Mimir</div>
        <div className={styles.mcardVal}>{fmt$(summary.traditional_cost || 0)}</div>
        <div className={styles.mcardSub}>traditional estimate</div>
      </div>

      <div className={styles.mcard}>
        <div className={styles.mcardLabel}>Savings</div>
        <div className={`${styles.mcardVal} ${summary.savings >= 0 ? styles.pos : styles.neg}`}>
          {fmt$(summary.savings || 0)}
        </div>
        <div className={`${styles.mcardSub} ${summary.savings >= 0 ? styles.pos : styles.neg}`}>
          {(summary.savings_percent || 0).toFixed(1)}% reduction
        </div>
      </div>
    </div>
  );
}

// ── Component Pie Chart ───────────────────────────────────────────────────────

interface ComponentPieProps {
  components: ComponentCosts;
}

function ComponentPie({ components }: ComponentPieProps) {
  const total = components.total_cost || 1e-9;
  const data = [
    components.embedding_cost || 0,
    components.llm_input_cost || 0,
    components.llm_output_cost || 0,
  ];
  const labels = ['Embedding', 'LLM input', 'LLM output'];
  const colors = [COLORS.blue, COLORS.teal, COLORS.amber];

  const chartData = {
    labels,
    datasets: [{
      data,
      backgroundColor: colors,
      borderWidth: 0,
      hoverOffset: 4,
    }],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '68%',
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: TooltipItem<'doughnut'>) => {
            const raw = item.raw as number;
            return `${item.label}: ${fmt$(raw)} (${((raw / total) * 100).toFixed(0)}%)`;
          },
        },
      },
    },
  };

  return (
    <div className={styles.ccard}>
      <div className={styles.ccardTitle}>Spend by component</div>
      <div className={styles.ccardSub}>Embedding · LLM input · LLM output</div>
      <div className={styles.chartWrap}>
        <Doughnut data={chartData} options={options} />
      </div>
      <div className={styles.legend}>
        {labels.map((l, i) => (
          <span key={l}>
            <span className={styles.swatch} style={{ background: colors[i] }} />
            {l} {((data[i] / total) * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Type Stack Chart ──────────────────────────────────────────────────────────

interface TypeStackProps {
  breakdown: QueryBreakdown[];
}

function TypeStack({ breakdown }: TypeStackProps) {
  if (!breakdown || breakdown.length === 0) {
    return (
      <div className={`${styles.ccard} ${styles.span2}`}>
        <div className={styles.ccardTitle}>Token spend by query type</div>
        <div className={styles.ccardSub}>What each query type actually costs, broken down</div>
        <div className={styles.empty}>No data available</div>
      </div>
    );
  }

  const labels = breakdown.map(b => b.query_type);
  const embed = breakdown.map(b => b.embedding_cost || 0);
  const llmIn = breakdown.map(b => b.llm_input_cost || 0);
  const llmOut = breakdown.map(b => b.llm_output_cost || 0);

  const chartData = {
    labels,
    datasets: [
      { label: 'Embedding', data: embed, backgroundColor: COLORS.blue, stack: 's' },
      { label: 'LLM input', data: llmIn, backgroundColor: COLORS.teal, stack: 's' },
      { label: 'LLM output', data: llmOut, backgroundColor: COLORS.amber, stack: 's' },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: TooltipItem<'bar'>) => {
            const raw = item.raw as number;
            return `${item.dataset.label}: ${fmt$(raw)}/query avg`;
          },
        },
      },
    },
    scales: {
      x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
      y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8', callback: (v: any) => fmt$(v) } },
    },
  };

  return (
    <div className={`${styles.ccard} ${styles.span2}`}>
      <div className={styles.ccardTitle}>Token spend by query type</div>
      <div className={styles.ccardSub}>What each query type actually costs, broken down</div>
      <div className={styles.chartWrap}>
        <Bar data={chartData} options={options} />
      </div>
      <div className={styles.legend}>
        <span><span className={styles.swatch} style={{ background: COLORS.blue }} />Embedding</span>
        <span><span className={styles.swatch} style={{ background: COLORS.teal }} />LLM input</span>
        <span><span className={styles.swatch} style={{ background: COLORS.amber }} />LLM output</span>
      </div>
    </div>
  );
}

// ── Component Bars (HTML) ─────────────────────────────────────────────────────

interface ComponentBarsProps {
  components: ComponentCosts;
}

function ComponentBars({ components }: ComponentBarsProps) {
  const total = components.total_cost || 1e-9;
  const rows = [
    { label: 'Embedding', val: components.embedding_cost || 0, color: COLORS.blue },
    { label: 'LLM input', val: components.llm_input_cost || 0, color: COLORS.teal },
    { label: 'LLM output', val: components.llm_output_cost || 0, color: COLORS.amber },
  ];

  return (
    <div className={styles.ccard}>
      <div className={styles.ccardTitle}>Cost breakdown detail</div>
      <div className={styles.ccardSub}>Proportional bar for each spend category</div>
      <div className={styles.cbarWrap}>
        {rows.map(r => {
          const pct = ((r.val / total) * 100).toFixed(1);
          return (
            <div key={r.label} className={styles.cbarRow}>
              <span className={styles.cbarLabel}>{r.label}</span>
              <div className={styles.cbar}>
                <div className={styles.cbarFill} style={{ width: `${pct}%`, background: r.color }} />
              </div>
              <span className={styles.cbarAmt} style={{ color: r.color }}>
                {fmt$(r.val)} <span style={{ color: '#94a3b8' }}>({pct}%)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Trend Chart ───────────────────────────────────────────────────────────────

interface TrendChartProps {
  daily: DailyMetrics[];
}

function TrendChart({ daily }: TrendChartProps) {
  if (!daily || daily.length === 0) {
    return (
      <div className={styles.ccard}>
        <div className={styles.ccardTitle}>Daily Mimir vs traditional cost</div>
        <div className={styles.ccardSub}>Shaded gap = savings</div>
        <div className={styles.empty}>No data available</div>
      </div>
    );
  }

  const chartData = {
    labels: daily.map(d => d.date),
    datasets: [
      {
        label: 'Mimir',
        data: daily.map(d => d.cost),
        borderColor: COLORS.blue,
        backgroundColor: COLORS.blueFade,
        fill: true,
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Traditional',
        data: daily.map(d => d.traditional_cost),
        borderColor: COLORS.gray,
        backgroundColor: COLORS.grayFade,
        fill: true,
        tension: 0.4,
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 0,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
        callbacks: {
          label: (item: TooltipItem<'line'>) => {
            const raw = item.raw as number;
            return `${item.dataset.label}: ${fmt$(raw)}`;
          },
        },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 9 } },
      y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8', callback: (v: any) => fmt$(v) } },
    },
  };

  return (
    <div className={styles.ccard}>
      <div className={styles.ccardTitle}>Daily Mimir vs traditional cost</div>
      <div className={styles.ccardSub}>Shaded gap = savings</div>
      <div className={styles.chartWrapLarge}>
        <Line data={chartData} options={options} />
      </div>
      <div className={styles.legend}>
        <span><span className={styles.swatch} style={{ background: COLORS.blue }} />Mimir</span>
        <span><span className={styles.swatch} style={{ background: COLORS.gray }} />Traditional est.</span>
      </div>
    </div>
  );
}

// ── ROI Chart ─────────────────────────────────────────────────────────────────

interface ROIChartProps {
  breakdown: QueryBreakdown[];
}

function ROIChart({ breakdown }: ROIChartProps) {
  if (!breakdown || breakdown.length === 0) {
    return (
      <div className={styles.ccard}>
        <div className={styles.ccardTitle}>Savings multiplier by query type</div>
        <div className={styles.ccardSub}>Traditional ÷ Mimir — higher is better</div>
        <div className={styles.empty}>No data available</div>
      </div>
    );
  }

  const labels = breakdown.map(b => b.query_type);
  const rois = breakdown.map(b => {
    const trad = (TRADITIONAL_TOKENS[b.query_type] || 5000) / 1000 * 0.001;
    const avg = b.count ? b.cost / b.count : 0.001;
    return avg > 0 ? parseFloat((trad / avg).toFixed(1)) : 0;
  });

  const chartData = {
    labels,
    datasets: [{
      data: rois,
      backgroundColor: rois.map(v => v >= 5 ? COLORS.teal : v >= 3 ? COLORS.blue : COLORS.amber),
      borderRadius: 4,
    }],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y' as const,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: TooltipItem<'bar'>) => {
            const raw = item.raw as number;
            return `${raw}x cheaper than traditional`;
          },
        },
      },
    },
    scales: {
      x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8', callback: (v: any) => `${v}x` }, min: 0 },
      y: { grid: { display: false }, ticks: { color: '#94a3b8' } },
    },
  };

  return (
    <div className={styles.ccard}>
      <div className={styles.ccardTitle}>Savings multiplier by query type</div>
      <div className={styles.ccardSub}>Traditional ÷ Mimir — higher is better</div>
      <div className={styles.chartWrapLarge}>
        <Bar data={chartData} options={options} />
      </div>
      <div className={styles.legend}>
        <span><span className={styles.swatch} style={{ background: COLORS.teal }} />Higher = more savings</span>
      </div>
    </div>
  );
}

// ── Waterfall Chart ───────────────────────────────────────────────────────────

interface WaterfallChartProps {
  summary: MetricsSummary;
  breakdown: QueryBreakdown[];
}

function WaterfallChart({ summary, breakdown }: WaterfallChartProps) {
  const base = summary.traditional_cost || 0;

  if (base === 0) {
    return (
      <div className={styles.ccard}>
        <div className={styles.ccardTitle}>Cost waterfall</div>
        <div className={styles.ccardSub}>Traditional total → reductions by category → Mimir total</div>
        <div className={styles.empty}>No data available</div>
      </div>
    );
  }

  const cats = ['Traditional'];
  const floats = [0];
  const bars = [base];
  const colors = [COLORS.gray];

  let running = base;
  (breakdown || []).forEach(b => {
    const saving = (TRADITIONAL_TOKENS[b.query_type] || 5000) / 1000 * 0.001 * b.count - b.cost;
    if (saving <= 0) return;
    cats.push(b.query_type + ' savings');
    floats.push(running - saving);
    bars.push(saving);
    colors.push(COLORS.teal);
    running -= saving;
  });

  cats.push('Mimir total');
  floats.push(0);
  bars.push(summary.total_cost || 0);
  colors.push(COLORS.blue);

  const chartData = {
    labels: cats,
    datasets: [
      { label: 'offset', data: floats, backgroundColor: 'transparent', borderColor: 'transparent', stack: 'w' },
      { label: 'value', data: bars, backgroundColor: colors, borderRadius: 3, stack: 'w' },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: TooltipItem<'bar'>) => {
            const raw = item.raw as number;
            return item.datasetIndex === 1 ? fmt$(raw) : '';
          },
        },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
      y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8', callback: (v: any) => fmt$(v) } },
    },
  };

  return (
    <div className={styles.ccard}>
      <div className={styles.ccardTitle}>Cost waterfall</div>
      <div className={styles.ccardSub}>Traditional total → reductions by category → Mimir total</div>
      <div className={styles.chartWrapMedium}>
        <Bar data={chartData} options={options} />
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function MetricsPage() {
  const [days, setDays] = useState(30);
  const { summary, daily, breakdown, components, loading } = useMetricsData(days);

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <Link to="/" className={styles.navLink}>← Back to graph</Link>
          <h1 className={styles.heading}>Metrics &amp; usage</h1>
        </div>
        <div className={styles.controls}>
          {[7, 30, 90].map(d => (
            <button
              key={d}
              className={`${styles.tBtn} ${days === d ? styles.active : ''}`}
              onClick={() => setDays(d)}
            >
              {d}d
            </button>
          ))}
        </div>
      </header>

      {loading ? (
        <div className={styles.spinnerWrap}>
          <div className={styles.spinner} />
        </div>
      ) : (
        <div className={styles.dash}>
          <SummaryCards summary={summary} />

          <div className={styles.sectionTitle}>Where the money goes</div>
          <div className={styles.grid3}>
            <ComponentPie components={components} />
            <TypeStack breakdown={breakdown} />
          </div>

          <ComponentBars components={components} />

          <div className={styles.sectionTitle}>Usage over time</div>
          <div className={styles.grid2}>
            <TrendChart daily={daily} />
            <ROIChart breakdown={breakdown} />
          </div>

          <div className={styles.sectionTitle}>Savings source breakdown</div>
          <WaterfallChart summary={summary} breakdown={breakdown} />
        </div>
      )}
    </div>
  );
}
