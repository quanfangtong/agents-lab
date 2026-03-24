export interface TableNode {
  name: string
  domain: string
  col_count: number
  has_data: boolean
}

export interface Edge {
  source: string
  column: string
  col_comment: string
  target: string
}

export interface Column {
  name: string
  type: string
  is_pk: boolean
  nullable: boolean
  comment: string | boolean
}

export interface GraphData {
  nodes: TableNode[]
  edges: Edge[]
  columns: Record<string, Column[]>
  stats: {
    tables: number
    total_columns: number
    edges: number
  }
}

export const DOMAIN_COLORS: Record<string, string> = {
  '公共基础': '#6366f1',
  '房源': '#f59e0b',
  '房间': '#10b981',
  '租客': '#ef4444',
  '合同': '#8b5cf6',
  '账单': '#06b6d4',
  '财务': '#f97316',
  '智能硬件': '#64748b',
}

export const DOMAINS = Object.keys(DOMAIN_COLORS)
