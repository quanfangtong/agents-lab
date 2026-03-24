import { graphData, outEdges, inEdges, DOMAIN_COLORS } from '../data/index.ts'
import type { Column } from '../data/index.ts'

const TABLE_NAME = 'qft_joint_tenants'

export function TransformDemo() {
  const node = graphData.nodes.find(n => n.name === TABLE_NAME)!
  const columns: Column[] = graphData.columns[TABLE_NAME] || []
  const outs = outEdges[TABLE_NAME] || []
  const ins = inEdges[TABLE_NAME] || []
  const fkCols = new Set(outs.map(e => e.column))
  const domainColor = DOMAIN_COLORS[node.domain] || '#8b949e'

  return (
    <div className="section">
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>转换过程</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 32 }}>
        以 <code>{TABLE_NAME}</code>（租客主表）为例，展示 MySQL 表结构如何转换为图数据库中的节点与边。
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto 1fr',
        gap: 0,
        alignItems: 'stretch',
        minHeight: 500,
      }}>
        {/* Left: MySQL columns */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '8px 0 0 8px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{
            padding: '12px 16px',
            background: 'var(--bg-elevated)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f0883e" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="3" y1="9" x2="21" y2="9" />
              <line x1="9" y1="9" x2="9" y2="21" />
            </svg>
            <span style={{ fontWeight: 600, fontSize: 14 }}>MySQL 表结构</span>
            <span style={{ color: 'var(--text-secondary)', fontSize: 12, marginLeft: 'auto' }}>
              {columns.length} 列
            </span>
          </div>

          <div style={{
            padding: '8px 0',
            background: 'var(--bg)',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{
              padding: '4px 16px',
              fontFamily: 'var(--mono)',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--accent)',
            }}>
              {TABLE_NAME}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
            {columns.map(col => {
              const isPk = col.is_pk
              const isFk = fkCols.has(col.name)
              return (
                <div key={col.name} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 16px',
                  fontSize: 12,
                  fontFamily: 'var(--mono)',
                  borderLeft: isFk ? '3px solid var(--accent)' : isPk ? '3px solid var(--yellow)' : '3px solid transparent',
                  background: isFk ? 'rgba(88,166,255,0.05)' : isPk ? 'rgba(210,153,34,0.05)' : 'transparent',
                }}>
                  <span style={{ width: 28, fontSize: 10, color: isPk ? 'var(--yellow)' : isFk ? 'var(--accent)' : 'transparent', fontWeight: 700 }}>
                    {isPk ? 'PK' : isFk ? 'FK' : ''}
                  </span>
                  <span style={{ flex: 1, color: 'var(--text)' }}>{col.name}</span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{col.type}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Center: Arrow */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 24px',
          gap: 12,
        }}>
          <div style={{
            writingMode: 'vertical-lr',
            fontSize: 11,
            color: 'var(--text-secondary)',
            letterSpacing: 2,
          }}>
            TRANSFORM
          </div>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <path d="M8 24h28M28 16l8 8-8 8" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div style={{
            writingMode: 'vertical-lr',
            fontSize: 11,
            color: 'var(--accent)',
            fontWeight: 600,
            letterSpacing: 2,
          }}>
            GRAPH
          </div>
        </div>

        {/* Right: Graph representation */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '0 8px 8px 0',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{
            padding: '12px 16px',
            background: 'var(--bg-elevated)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" strokeWidth="2">
              <circle cx="12" cy="5" r="3" />
              <circle cx="5" cy="19" r="3" />
              <circle cx="19" cy="19" r="3" />
              <line x1="12" y1="8" x2="5" y2="16" />
              <line x1="12" y1="8" x2="19" y2="16" />
            </svg>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Property Graph</span>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
            {/* Main TableNode */}
            <div style={{
              background: domainColor + '15',
              border: `2px solid ${domainColor}`,
              borderRadius: 8,
              padding: 16,
              marginBottom: 16,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span className="badge" style={{
                  background: domainColor + '22',
                  color: domainColor,
                  border: `1px solid ${domainColor}44`,
                  fontSize: 10,
                }}>
                  :TableNode
                </span>
                <span className="badge" style={{
                  background: 'rgba(88,166,255,0.15)',
                  color: 'var(--accent)',
                  fontSize: 10,
                }}>
                  {node.domain}
                </span>
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>
                {TABLE_NAME}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                {node.col_count} 列 | {node.has_data ? '有数据' : '无数据'}
              </div>
            </div>

            {/* Column Nodes (first 6 as sample) */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
                ColumnNode 示例（{columns.length} 个）
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {columns.slice(0, 8).map(col => (
                  <div key={col.name} style={{
                    padding: '4px 10px',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    fontSize: 11,
                    fontFamily: 'var(--mono)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}>
                    {col.is_pk && <span style={{ color: 'var(--yellow)', fontSize: 9, fontWeight: 700 }}>PK</span>}
                    <span style={{ color: 'var(--text)' }}>{col.name}</span>
                    <span style={{ color: 'var(--text-secondary)', fontSize: 10 }}>{col.type}</span>
                  </div>
                ))}
                {columns.length > 8 && (
                  <div style={{
                    padding: '4px 10px',
                    background: 'var(--bg)',
                    border: '1px dashed var(--border)',
                    borderRadius: 4,
                    fontSize: 11,
                    color: 'var(--text-secondary)',
                  }}>
                    +{columns.length - 8} more
                  </div>
                )}
              </div>
            </div>

            {/* REFERENCES edges */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--green)', marginBottom: 8 }}>
                出边 [:REFERENCES] ({outs.length})
              </div>
              {outs.map((e, i) => {
                const targetNode = graphData.nodes.find(n => n.name === e.target)
                const targetColor = targetNode ? DOMAIN_COLORS[targetNode.domain] || '#8b949e' : '#8b949e'
                return (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 10px',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    marginBottom: 4,
                    fontSize: 12,
                  }}>
                    <span style={{
                      fontFamily: 'var(--mono)',
                      color: 'var(--accent)',
                      fontSize: 11,
                    }}>
                      {e.column}
                    </span>
                    <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
                      <path d="M2 6h14M12 2l4 4-4 4" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: targetColor + '15',
                      border: `1px solid ${targetColor}44`,
                      fontFamily: 'var(--mono)',
                      fontSize: 11,
                      color: targetColor,
                    }}>
                      {e.target}
                    </span>
                    {e.col_comment && (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                        {e.col_comment}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Incoming edges */}
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--orange)', marginBottom: 8 }}>
                入边 [:REFERENCED_BY] ({ins.length})
              </div>
              {ins.map((e, i) => {
                const sourceNode = graphData.nodes.find(n => n.name === e.source)
                const sourceColor = sourceNode ? DOMAIN_COLORS[sourceNode.domain] || '#8b949e' : '#8b949e'
                return (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 10px',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    marginBottom: 4,
                    fontSize: 12,
                  }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: sourceColor + '15',
                      border: `1px solid ${sourceColor}44`,
                      fontFamily: 'var(--mono)',
                      fontSize: 11,
                      color: sourceColor,
                    }}>
                      {e.source}
                    </span>
                    <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
                      <path d="M2 6h14M12 2l4 4-4 4" stroke="var(--orange)" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <span style={{
                      fontFamily: 'var(--mono)',
                      color: 'var(--accent)',
                      fontSize: 11,
                    }}>
                      {e.column}
                    </span>
                    {e.col_comment && (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                        {e.col_comment}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Cypher representation */}
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
                Cypher 表示
              </div>
              <pre style={{ fontSize: 11, lineHeight: 1.8 }}>
{`// 创建 TableNode
CREATE (:TableNode {
  name: "${TABLE_NAME}",
  domain: "${node.domain}",
  col_count: ${node.col_count}
})

// 创建 REFERENCES 边
${outs.map(e => `MATCH (a:TableNode {name:"${e.source}"}), (b:TableNode {name:"${e.target}"})
CREATE (a)-[:REFERENCES {column:"${e.column}", comment:"${e.col_comment}"}]->(b)`).join('\n\n')}`}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
