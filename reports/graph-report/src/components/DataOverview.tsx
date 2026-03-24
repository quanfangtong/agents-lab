import { useState, useMemo } from 'react'
import { graphData, outEdges, inEdges, DOMAIN_COLORS, DOMAINS } from '../data/index.ts'
import type { TableNode, Column, Edge } from '../data/index.ts'

function TableModal({ table, onClose }: { table: TableNode; onClose: () => void }) {
  const columns: Column[] = graphData.columns[table.name] || []
  const outs: Edge[] = outEdges[table.name] || []
  const ins: Edge[] = inEdges[table.name] || []
  const domainColor = DOMAIN_COLORS[table.domain] || '#8b949e'

  // Build FK column set from outEdges
  const fkColumns = new Set(outs.map(e => e.column))

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ position: 'relative' }}
        onClick={e => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose}>&times;</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <span className="badge" style={{
            background: domainColor + '22',
            color: domainColor,
            border: `1px solid ${domainColor}44`,
          }}>
            {table.domain}
          </span>
          <h2 style={{ fontSize: 18 }}>{table.name}</h2>
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
            {columns.length} 列
          </span>
        </div>

        {/* Columns table */}
        <div style={{ overflowX: 'auto', marginBottom: 20 }}>
          <table>
            <thead>
              <tr>
                <th>列名</th>
                <th>类型</th>
                <th>PK</th>
                <th>FK</th>
                <th>可空</th>
                <th>注释</th>
              </tr>
            </thead>
            <tbody>
              {columns.map(col => (
                <tr key={col.name}>
                  <td style={{ color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12 }}>
                    {col.name}
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{col.type}</td>
                  <td>
                    {col.is_pk && (
                      <span style={{ color: 'var(--yellow)', fontWeight: 600, fontSize: 11 }}>PK</span>
                    )}
                  </td>
                  <td>
                    {fkColumns.has(col.name) && (
                      <span style={{ color: 'var(--accent)', fontWeight: 600, fontSize: 11 }}>FK</span>
                    )}
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {col.nullable ? 'YES' : 'NO'}
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {col.comment === true ? '-' : (col.comment || '-')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Edges */}
        {outs.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 14, marginBottom: 8, color: 'var(--green)' }}>
              出边 (REFERENCES) &mdash; {outs.length} 条
            </h3>
            {outs.map((e, i) => (
              <div key={i} style={{
                padding: '6px 12px',
                background: 'var(--bg)',
                borderRadius: 4,
                marginBottom: 4,
                fontSize: 13,
                fontFamily: 'var(--mono)',
              }}>
                <span style={{ color: 'var(--accent)' }}>{e.column}</span>
                <span style={{ color: 'var(--text-secondary)', margin: '0 8px' }}>&rarr;</span>
                <span style={{ color: 'var(--text)' }}>{e.target}</span>
                {e.col_comment && (
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 12, fontFamily: 'var(--sans)', fontSize: 12 }}>
                    ({e.col_comment})
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {ins.length > 0 && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8, color: 'var(--orange)' }}>
              入边 (REFERENCED BY) &mdash; {ins.length} 条
            </h3>
            {ins.map((e, i) => (
              <div key={i} style={{
                padding: '6px 12px',
                background: 'var(--bg)',
                borderRadius: 4,
                marginBottom: 4,
                fontSize: 13,
                fontFamily: 'var(--mono)',
              }}>
                <span style={{ color: 'var(--text)' }}>{e.source}</span>
                <span style={{ color: 'var(--text-secondary)', margin: '0 8px' }}>&rarr;</span>
                <span style={{ color: 'var(--accent)' }}>{e.column}</span>
                {e.col_comment && (
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 12, fontFamily: 'var(--sans)', fontSize: 12 }}>
                    ({e.col_comment})
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function DataOverview() {
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null)
  const [modalTable, setModalTable] = useState<TableNode | null>(null)

  const filteredNodes = useMemo(() => {
    if (!selectedDomain) return graphData.nodes
    return graphData.nodes.filter(n => n.domain === selectedDomain)
  }, [selectedDomain])

  return (
    <div className="section">
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>数据概览</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>
        全房通 MySQL 数据库包含 {graphData.stats.tables} 张表、{graphData.stats.total_columns} 个字段、
        {graphData.stats.edges} 条表间引用关系，横跨 8 个业务域。
      </p>

      {/* Domain filter chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 24 }}>
        <span
          className={`chip ${selectedDomain === null ? 'active' : ''}`}
          style={{
            background: 'var(--bg-elevated)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
          }}
          onClick={() => setSelectedDomain(null)}
        >
          全部 ({graphData.nodes.length})
        </span>
        {DOMAINS.map(domain => {
          const color = DOMAIN_COLORS[domain]
          const count = graphData.nodes.filter(n => n.domain === domain).length
          return (
            <span
              key={domain}
              className={`chip ${selectedDomain === domain ? 'active' : ''}`}
              style={{
                background: color + '18',
                color,
                border: `1px solid ${color}44`,
              }}
              onClick={() => setSelectedDomain(selectedDomain === domain ? null : domain)}
            >
              {domain} ({count})
            </span>
          )
        })}
      </div>

      {/* Table cards grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: 12,
      }}>
        {filteredNodes.map(node => {
          const outs = outEdges[node.name] || []
          const ins = inEdges[node.name] || []
          const domainColor = DOMAIN_COLORS[node.domain] || '#8b949e'

          return (
            <div
              key={node.name}
              className="card"
              style={{
                cursor: 'pointer',
                transition: 'border-color 0.2s, transform 0.2s',
                borderColor: 'var(--border)',
              }}
              onClick={() => setModalTable(node)}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.borderColor = domainColor
                ;(e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'
                ;(e.currentTarget as HTMLElement).style.transform = 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span className="badge" style={{
                  background: domainColor + '22',
                  color: domainColor,
                  border: `1px solid ${domainColor}44`,
                  fontSize: 10,
                }}>
                  {node.domain}
                </span>
                {node.has_data && (
                  <span style={{ fontSize: 10, color: 'var(--green)' }}>&#9679; 有数据</span>
                )}
              </div>

              <div style={{
                fontFamily: 'var(--mono)',
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--text)',
                marginBottom: 10,
                wordBreak: 'break-all',
              }}>
                {node.name}
              </div>

              <div style={{
                display: 'flex',
                gap: 16,
                fontSize: 12,
                color: 'var(--text-secondary)',
              }}>
                <span>{node.col_count} 列</span>
                <span style={{ color: 'var(--green)' }}>
                  &#8593; {outs.length} 出边
                </span>
                <span style={{ color: 'var(--orange)' }}>
                  &#8595; {ins.length} 入边
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Modal */}
      {modalTable && (
        <TableModal table={modalTable} onClose={() => setModalTable(null)} />
      )}
    </div>
  )
}
