import cytoscape from 'cytoscape';

/**
 * Simple physics simulation using requestAnimationFrame.
 * Applies repulsive and attractive forces between nodes.
 */
export class PhysicsEngine {
  private cy: cytoscape.Core;
  private animationId: number | null = null;
  private running = false;
  private velocities: Map<string, { x: number; y: number }> = new Map();

  // Tunable parameters
  private static readonly REST_LENGTH = 120;
  private static readonly SPRING_STRENGTH = 0.002;
  private static readonly DAMPING = 0.85;

  constructor(cy: cytoscape.Core) {
    this.cy = cy;
  }

  start(repulsionStrength = 10000) {
    if (this.running) return;
    this.running = true;
    this.tick(repulsionStrength);
  }

  stop() {
    this.running = false;
    if (this.animationId !== null) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    this.velocities.clear();
  }

  private tick(repulsionStrength: number) {
    if (!this.running) return;

    const nodes = this.cy.nodes();
    const edges = this.cy.edges();

    // Initialize velocities for any new nodes
    nodes.forEach(node => {
      if (!this.velocities.has(node.id())) {
        this.velocities.set(node.id(), { x: 0, y: 0 });
      }
    });

    // Accumulate forces for each node
    const forces: Map<string, { x: number; y: number }> = new Map();
    nodes.forEach(node => {
      forces.set(node.id(), { x: 0, y: 0 });
    });

    // Apply attractive forces along edges (spring with rest length)
    edges.forEach(edge => {
      const source = edge.source();
      const target = edge.target();
      if (!source || !target) return;

      const sPos = source.position();
      const tPos = target.position();
      const dx = tPos.x - sPos.x;
      const dy = tPos.y - sPos.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;

      // Use the larger of the two nodes' radii to scale rest length
      const sSize = Math.max(source.width(), source.height()) / 2;
      const tSize = Math.max(target.width(), target.height()) / 2;
      const restLength = PhysicsEngine.REST_LENGTH + sSize + tSize;

      // Spring force: F = k * (dist - restLength)
      // Pulls when stretched, pushes when compressed
      const displacement = dist - restLength;
      const force = PhysicsEngine.SPRING_STRENGTH * displacement;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      const sForce = forces.get(source.id())!;
      sForce.x += fx;
      sForce.y += fy;
      const tForce = forces.get(target.id())!;
      tForce.x -= fx;
      tForce.y -= fy;
    });

    // Apply repulsive forces between all node pairs
    const nodeArray = nodes.toArray();
    for (let i = 0; i < nodeArray.length; i++) {
      for (let j = i + 1; j < nodeArray.length; j++) {
        const a = nodeArray[i];
        const b = nodeArray[j];
        const aPos = a.position();
        const bPos = b.position();
        const dx = bPos.x - aPos.x;
        const dy = bPos.y - aPos.y;
        const distSq = dx * dx + dy * dy || 1;
        const dist = Math.sqrt(distSq);

        // Repulsive force (inverse square), scaled by node sizes
        // so large nodes repel more strongly and don't collapse together
        const aSize = Math.max(a.width(), a.height()) / 2;
        const bSize = Math.max(b.width(), b.height()) / 2;
        const minDist = Math.max(aSize + bSize, 10);
        const clampedDistSq = Math.max(distSq, minDist * minDist);
        const sizeFactor = (aSize + bSize) / 80; // 80 = 2 * base radius (40)
        const force = (repulsionStrength * sizeFactor) / clampedDistSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        const aForce = forces.get(a.id())!;
        aForce.x -= fx;
        aForce.y -= fy;
        const bForce = forces.get(b.id())!;
        bForce.x += fx;
        bForce.y += fy;
      }
    }

    // Apply velocity damping, integrate forces into velocity, and update positions
    nodes.forEach(node => {
      const vel = this.velocities.get(node.id())!;
      const force = forces.get(node.id())!;

      // Integrate force into velocity
      vel.x += force.x;
      vel.y += force.y;

      // Damp velocity
      vel.x *= PhysicsEngine.DAMPING;
      vel.y *= PhysicsEngine.DAMPING;

      // Update position from velocity
      const pos = node.position();
      node.position({ x: pos.x + vel.x, y: pos.y + vel.y });
    });

    this.animationId = requestAnimationFrame(() => this.tick(repulsionStrength));
  }
}
