import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Network, DataSet } from 'vis-network/standalone'
import { graphData, outEdges, inEdges, DOMAIN_COLORS, DOMAINS } from '../data/index.ts'
import type { TableNode, Column, Edge } from '../data/index.ts'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>

// Deduplicate edges: keep one per source->target pair
function deduplicateEdges(edges: Edge[]): Edge[] {
  const seen = new Set<string>()
  const result: Edge[] = []
  for (const e of edges) {
    const key = `${e.source}->${e.target}`
    if (!seen.has(key)) {
      seen.add(key)
      result.push(e)
    }
  }
  return result
}

function TableDetailModal({ table, onClose }: { table: TableNode; onClose: () => void }) {
  const columns: Column[] = graphData.columns[table.name] || []
  const outs: Edge[] = outEdges[table.name] || []
  const ins: Edge[] = inEdges[table.name] || []
  const domainColor = DOMAIN_COLORS[table.domain] || '#8b949e'
  const fkColumns = new Set(outs.map(e => e.column))

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ position: 'relative' }} onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>&times;</button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <span className="badge" style={{ background: domainColor + '22', color: domainColor, border: `1px solid ${domainColor}44` }}>
            {table.domain}
          </span>
          <h2 style={{ fontSize: 18 }}>{table.name}</h2>
        </div>
        <div style={{ overflowX: 'auto', marginBottom: 16 }}>
          <table>
            <thead>
              <tr><th>列名</th><th>类型</th><th>PK</th><th>FK</th></tr>
            </thead>
            <tbody>
              {columns.map(col => (
                <tr key={col.name}>
                  <td style={{ color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12 }}>{col.name}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{col.type}</td>
                  <td>{col.is_pk && <span style={{ color: 'var(--yellow)', fontWeight: 600, fontSize: 11 }}>PK</span>}</td>
                  <td>{fkColumns.has(col.name) && <span style={{ color: 'var(--accent)', fontWeight: 600, fontSize: 11 }}>FK</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {outs.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <h3 style={{ fontSize: 13, color: 'var(--green)', marginBottom: 6 }}>出边 ({outs.length})</h3>
            {outs.map((e, i) => (
              <div key={i} style={{ fontSize: 12, fontFamily: 'var(--mono)', padding: '2px 0' }}>
                <span style={{ color: 'var(--accent)' }}>{e.column}</span>
                <span style={{ color: 'var(--text-secondary)', margin: '0 6px' }}>&rarr;</span>
                <span>{e.target}</span>
              </div>
            ))}
          </div>
        )}
        {ins.length > 0 && (
          <div>
            <h3 style={{ fontSize: 13, color: 'var(--orange)', marginBottom: 6 }}>入边 ({ins.length})</h3>
            {ins.map((e, i) => (
              <div key={i} style={{ fontSize: 12, fontFamily: 'var(--mono)', padding: '2px 0' }}>
                <span>{e.source}</span>
                <span style={{ color: 'var(--text-secondary)', margin: '0 6px' }}>&rarr;</span>
                <span style={{ color: 'var(--accent)' }}>{e.column}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function GraphVisualization() {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState<string>('')
  const [physicsEnabled, setPhysicsEnabled] = useState(true)
  const [selectedNode, setSelectedNode] = useState<TableNode | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [modalTable, setModalTable] = useState<TableNode | null>(null)

  const dedupedEdges = useMemo(() => deduplicateEdges(graphData.edges), [])

  // Build vis datasets
  const { visNodes, visEdges } = useMemo(() => {
    const nodes = new DataSet(
      graphData.nodes.map(n => ({
        id: n.name,
        label: n.name.replace('qft_joint_', 'j_').replace('qft_', ''),
        title: `${n.name}\n${n.domain} | ${n.col_count}列`,
        color: {
          background: DOMAIN_COLORS[n.domain] || '#8b949e',
          border: DOMAIN_COLORS[n.domain] || '#8b949e',
          highlight: { background: '#58a6ff', border: '#58a6ff' },
          hover: { background: DOMAIN_COLORS[n.domain] || '#8b949e', border: '#e6edf3' },
        },
        size: Math.max(12, Math.min(35, n.col_count / 3)),
        font: { color: '#e6edf3', size: 10, face: 'system-ui' },
        borderWidth: 2,
      }))
    )

    const edges = new DataSet(
      dedupedEdges.map((e, i) => ({
        id: `e${i}`,
        from: e.source,
        to: e.target,
        arrows: 'to',
        color: { color: '#30363d', highlight: '#58a6ff', hover: '#58a6ff' },
        width: 1,
        title: `${e.source}.${e.column} → ${e.target}`,
      }))
    )

    return { visNodes: nodes, visEdges: edges }
  }, [dedupedEdges])

  // Initialize vis-network
  useEffect(() => {
    if (!containerRef.current) return

    const network = new Network(containerRef.current, { nodes: visNodes, edges: visEdges }, {
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -80,
          centralGravity: 0.01,
          springLength: 150,
          springConstant: 0.04,
          damping: 0.5,
        },
        stabilization: { iterations: 200, updateInterval: 25 },
      },
      nodes: {
        shape: 'dot',
        borderWidth: 2,
        shadow: { enabled: true, size: 8, color: 'rgba(0,0,0,0.3)' },
      },
      edges: {
        smooth: { enabled: true, type: 'continuous', roundness: 0.5 },
        selectionWidth: 2,
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        navigationButtons: false,
        keyboard: false,
      },
    })

    networkRef.current = network
    return () => { network.destroy() }
  }, [visNodes, visEdges])

  // Toggle physics
  useEffect(() => {
    networkRef.current?.setOptions({ physics: { enabled: physicsEnabled } })
  }, [physicsEnabled])

  // Click handler
  useEffect(() => {
    const network = networkRef.current
    if (!network) return

    const clickHandler = (params: { nodes: string[] }) => {
      if (params.nodes.length > 0) {
        const nodeName = params.nodes[0]
        const node = graphData.nodes.find(n => n.name === nodeName) || null
        setSelectedNode(node)
      } else {
        setSelectedNode(null)
      }
    }

    network.on('click', clickHandler)
    return () => { network.off('click', clickHandler) }
  }, [])

  // Search & filter
  const handleSearch = useCallback(() => {
    if (!networkRef.current) return
    const term = search.trim().toLowerCase()
    if (!term) {
      networkRef.current.fit({ animation: true })
      return
    }
    const matching = graphData.nodes
      .filter(n => n.name.toLowerCase().includes(term))
      .map(n => n.name)
    if (matching.length > 0) {
      networkRef.current.selectNodes(matching)
      networkRef.current.focus(matching[0], { scale: 1.2, animation: true })
    }
  }, [search])

  const handleDomainFilter = useCallback((domain: string) => {
    setDomainFilter(domain)
    if (!networkRef.current) return
    if (!domain) {
      // Show all - restore original colors
      graphData.nodes.forEach(n => {
        const c = DOMAIN_COLORS[n.domain] || '#8b949e'
        visNodes.update({
          id: n.name,
          color: { background: c, border: c, highlight: { background: '#58a6ff', border: '#58a6ff' }, hover: { background: c, border: '#e6edf3' } },
          font: { color: '#e6edf3', size: 10, face: 'system-ui' },
        } as AnyRecord)
      })
      return
    }
    graphData.nodes.forEach(n => {
      const match = n.domain === domain
      const c = DOMAIN_COLORS[n.domain] || '#8b949e'
      visNodes.update({
        id: n.name,
        color: {
          background: match ? c : '#21262d',
          border: match ? c : '#21262d',
          highlight: { background: '#58a6ff', border: '#58a6ff' },
          hover: { background: c, border: '#e6edf3' },
        },
        font: { color: match ? '#e6edf3' : '#30363d', size: 10, face: 'system-ui' },
      } as AnyRecord)
    })
  }, [visNodes])

  const handleReset = useCallback(() => {
    setSearch('')
    setDomainFilter('')
    setSelectedNode(null)
    graphData.nodes.forEach(n => {
      const c = DOMAIN_COLORS[n.domain] || '#8b949e'
      visNodes.update({
        id: n.name,
        color: { background: c, border: c, highlight: { background: '#58a6ff', border: '#58a6ff' }, hover: { background: c, border: '#e6edf3' } },
        font: { color: '#e6edf3', size: 10, face: 'system-ui' },
      } as AnyRecord)
    })
    networkRef.current?.fit({ animation: true })
  }, [visNodes])

  // Sidebar detail for selected node
  const selectedOuts = selectedNode ? (outEdges[selectedNode.name] || []) : []
  const selectedIns = selectedNode ? (inEdges[selectedNode.name] || []) : []
  const selectedCols = selectedNode ? (graphData.columns[selectedNode.name] || []) : []

  return (
    <div style={{ height: 'calc(100vh - 45px)', display: 'flex', flexDirection: 'column' }}>
      {/* Control bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 16px',
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        flexWrap: 'wrap',
      }}>
        <input
          type="text"
          placeholder="搜索表名..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          style={{
            padding: '6px 12px',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            color: 'var(--text)',
            fontSize: 13,
            outline: 'none',
            width: 200,
          }}
        />
        <button onClick={handleSearch} style={{
          padding: '6px 12px',
          background: 'var(--accent)',
          color: '#0d1117',
          border: 'none',
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 600,
        }}>
          搜索
        </button>

        <select
          value={domainFilter}
          onChange={e => handleDomainFilter(e.target.value)}
          style={{
            padding: '6px 12px',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            color: 'var(--text)',
            fontSize: 13,
            outline: 'none',
          }}
        >
          <option value="">全部域</option>
          {DOMAINS.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <button onClick={handleReset} style={{
          padding: '6px 12px',
          background: 'var(--bg-elevated)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          fontSize: 12,
        }}>
          重置
        </button>

        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
          <input
            type="checkbox"
            checked={physicsEnabled}
            onChange={e => setPhysicsEnabled(e.target.checked)}
            style={{ accentColor: 'var(--accent)' }}
          />
          物理模拟
        </label>

        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
          {graphData.nodes.length} 节点 | {dedupedEdges.length} 边
        </span>
      </div>

      {/* Main content: graph + optional detail panel */}
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
        {/* Graph container */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            minHeight: 400,
            background: 'var(--bg)',
          }}
        />

        {/* Detail panel when node selected */}
        {selectedNode && (
          <div className="detail-panel" style={{
            width: 320,
            borderLeft: '1px solid var(--border)',
            background: 'var(--bg-card)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div>
                <span className="badge" style={{
                  background: (DOMAIN_COLORS[selectedNode.domain] || '#8b949e') + '22',
                  color: DOMAIN_COLORS[selectedNode.domain] || '#8b949e',
                  border: `1px solid ${(DOMAIN_COLORS[selectedNode.domain] || '#8b949e')}44`,
                  fontSize: 10,
                  marginRight: 8,
                }}>
                  {selectedNode.domain}
                </span>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  fontSize: 16,
                  cursor: 'pointer',
                  padding: '2px 6px',
                }}
              >
                &times;
              </button>
            </div>

            <div style={{ padding: '12px 16px', overflowY: 'auto', flex: 1 }}>
              <h3 style={{ fontSize: 14, fontFamily: 'var(--mono)', marginBottom: 12, wordBreak: 'break-all' }}>
                {selectedNode.name}
              </h3>

              {/* Column list (first 15) */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                  字段 ({selectedCols.length})
                </div>
                {selectedCols.slice(0, 15).map(col => (
                  <div key={col.name} style={{
                    fontSize: 11,
                    fontFamily: 'var(--mono)',
                    padding: '2px 0',
                    display: 'flex',
                    gap: 6,
                  }}>
                    {col.is_pk && <span style={{ color: 'var(--yellow)', fontSize: 9, fontWeight: 700 }}>PK</span>}
                    <span style={{ color: 'var(--text)' }}>{col.name}</span>
                    <span style={{ color: 'var(--text-secondary)', fontSize: 10, marginLeft: 'auto' }}>{col.type}</span>
                  </div>
                ))}
                {selectedCols.length > 15 && (
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                    +{selectedCols.length - 15} more...
                  </div>
                )}
              </div>

              {/* Edges */}
              {selectedOuts.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--green)', marginBottom: 4 }}>
                    出边 ({selectedOuts.length})
                  </div>
                  {selectedOuts.map((e, i) => (
                    <div key={i} style={{ fontSize: 11, fontFamily: 'var(--mono)', padding: '2px 0' }}>
                      <span style={{ color: 'var(--accent)' }}>{e.column}</span>
                      <span style={{ color: 'var(--text-secondary)' }}> &rarr; </span>
                      <span>{e.target}</span>
                    </div>
                  ))}
                </div>
              )}
              {selectedIns.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--orange)', marginBottom: 4 }}>
                    入边 ({selectedIns.length})
                  </div>
                  {selectedIns.map((e, i) => (
                    <div key={i} style={{ fontSize: 11, fontFamily: 'var(--mono)', padding: '2px 0' }}>
                      <span>{e.source}</span>
                      <span style={{ color: 'var(--text-secondary)' }}> &rarr; </span>
                      <span style={{ color: 'var(--accent)' }}>{e.column}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* "查看全部" button */}
              <button
                onClick={() => { setModalTable(selectedNode); setShowModal(true) }}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'var(--accent-bg)',
                  color: 'var(--accent)',
                  border: '1px solid rgba(88,166,255,0.3)',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  marginTop: 8,
                }}
              >
                查看全部字段与关系
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Legend bar at bottom */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '6px 16px',
        background: 'var(--bg-card)',
        borderTop: '1px solid var(--border)',
        flexWrap: 'wrap',
        fontSize: 11,
        color: 'var(--text-secondary)',
      }}>
        <span style={{ fontWeight: 600, color: 'var(--text)' }}>图例：</span>
        {DOMAINS.map(d => (
          <span key={d} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: DOMAIN_COLORS[d],
              display: 'inline-block',
            }} />
            {d}
          </span>
        ))}
        <span style={{ marginLeft: 16 }}>节点大小 = 列数</span>
        <span>箭头 = REFERENCES</span>
      </div>

      {/* Full modal */}
      {showModal && modalTable && (
        <TableDetailModal table={modalTable} onClose={() => { setShowModal(false); setModalTable(null) }} />
      )}
    </div>
  )
}
