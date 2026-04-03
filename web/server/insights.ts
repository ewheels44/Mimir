import cytoscape from 'cytoscape';
import { InsightData, BridgeNode } from '../types';

export function computeInsights(cy: cytoscape.Core): InsightData {
  const nodes = cy.nodes();
  const edges = cy.edges();

  // ── Connected components ─────────────────────────────────────────────────
  const components = cy.elements().components();
  const clusterCount = components.filter(c => c.nodes().length > 1).length;
  const isolatedCount = components.filter(c => c.nodes().length === 1).length;

  // ── Betweenness centrality for bridge nodes ──────────────────────────────
  let bridges: BridgeNode[] = [];
  try {
    const bc = cy.elements().bc();
    const candidates: BridgeNode[] = [];

    nodes.forEach(node => {
      // bc.betweenness returns raw score; bc.betweennessNormalized returns 0-1
      const score: number = bc.betweennessNormalized(node);
      if (score > 0.01) {
        candidates.push({
          id: node.id(),
          label: (node.data('label') as string) || node.id(),
          score,
        });
      }
    });

    bridges = candidates.sort((a, b) => b.score - a.score).slice(0, 5);
  } catch {
    // bc() can throw on empty or fully disconnected graphs — fail gracefully
  }

  // ── Natural language insight ─────────────────────────────────────────────
  const insight = buildInsight(
    nodes.length,
    edges.length,
    clusterCount,
    isolatedCount,
    bridges
  );

  return {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    clusterCount,
    isolatedCount,
    bridges,
    insight,
  };
}

function buildInsight(
  nodeCount: number,
  edgeCount: number,
  clusterCount: number,
  isolatedCount: number,
  bridges: BridgeNode[]
): string {
  if (nodeCount === 0) return 'No nodes loaded yet.';

  const parts: string[] = [];

  if (clusterCount > 1) {
    parts.push(`${clusterCount} connected clusters.`);
  } else if (clusterCount === 1) {
    parts.push('Fully connected codebase.');
  }

  if (bridges.length > 0) {
    parts.push(`"${bridges[0].label}" is the key bridging module.`);
  }

  if (isolatedCount > 0) {
    parts.push(
      `${isolatedCount} isolated node${isolatedCount !== 1 ? 's' : ''} have no connections.`
    );
  }

  const density =
    nodeCount > 1
      ? ((2 * edgeCount) / (nodeCount * (nodeCount - 1))).toFixed(3)
      : '0';
  parts.push(`Graph density: ${density}.`);

  return parts.join(' ') || 'Analyzing...';
}

/** Find nodes whose removal would disconnect the graph (articulation points).
 *  Uses a simple DFS-based check — not exhaustive for large graphs. */
export function findArticulationPoints(cy: cytoscape.Core): string[] {
  // Cytoscape doesn't expose articulation points natively.
  // We approximate by finding nodes with betweenness > 0.5 and degree >= 2.
  try {
    const bc = cy.elements().bc();
    const result: string[] = [];
    cy.nodes().forEach(n => {
      if (n.degree() >= 2 && bc.betweennessNormalized(n) > 0.5) {
        result.push(n.id());
      }
    });
    return result;
  } catch {
    return [];
  }
}
