import rawData from './graphData.json'
import type { GraphData, Edge } from './types'

export const graphData = rawData as GraphData

// 预计算出入边索引
export const outEdges: Record<string, Edge[]> = {}
export const inEdges: Record<string, Edge[]> = {}

graphData.edges.forEach(e => {
  if (!outEdges[e.source]) outEdges[e.source] = []
  outEdges[e.source].push(e)
  if (!inEdges[e.target]) inEdges[e.target] = []
  inEdges[e.target].push(e)
})

export { DOMAIN_COLORS, DOMAINS } from './types'
export type { TableNode, Edge, Column, GraphData } from './types'
