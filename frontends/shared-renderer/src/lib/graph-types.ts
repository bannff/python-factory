export interface GraphNode {
  id: string;
  name: string;
  type: string;
  color: string;
  val: number;
  properties?: Record<string, unknown>;
}

export interface GraphLink {
  source: string;
  target: string;
  label?: string;
}

export interface BoundedGraphContext {
  query_ref: string;
  neighborhood_limit: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
}
