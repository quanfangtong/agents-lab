import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Network, DataSet } from 'vis-network/standalone'
import { graphData, outEdges, inEdges, DOMAIN_COLORS, DOMAINS } from '../data/index.ts'
import type { Edge } from '../data/index.ts'

function deduplicateEdges(edges: Edge[]): Edge[] {
  const seen = new Set<string>()
  return edges.filter(e => {
    const key = `${e.source}->${e.target}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function computeHops(startName: string): { hop1: Set<string>; hop2: Set<string> } {
  const hop1 = new Set<string>()
  const hop2 = new Set<string>()
  const getNeighbors = (name: string): string[] => {
    const outs = (outEdges[name] || []).map(e => e.target)
    const ins = (inEdges[name] || []).map(e => e.source)
    return [...new Set([...outs, ...ins])]
  }
  getNeighbors(startName).forEach(n => hop1.add(n))
  hop1.forEach(n1 => {
    getNeighbors(n1).forEach(n2 => {
      if (n2 !== startName && !hop1.has(n2)) hop2.add(n2)
    })
  })
  return { hop1, hop2 }
}

// ===== 多个真实业务场景 =====
interface DemoScenario {
  id: string
  question: string
  difficulty: string
  difficultyColor: string
  description: string
  steps: {
    title: string
    description: string
    detail: string
    highlights: string[]
    highlightEdges: string[]
  }[]
}

const SCENARIOS: DemoScenario[] = [
  {
    id: 'simple',
    question: '城东门店有多少套合租房源？',
    difficulty: '简单',
    difficultyColor: '#7ee787',
    description: '单表查询 — 只需 1 张表，无需 JOIN',
    steps: [
      {
        title: '提取关键词',
        description: '从问题中识别实体和意图',
        detail: '• "城东门店" → 门店名称 → qft_store\n• "合租房源" → 合租房源表 → qft_joint_housing\n• "多少套" → COUNT 聚合',
        highlights: ['qft_store', 'qft_joint_housing'],
        highlightEdges: [],
      },
      {
        title: '图遍历：确认关系',
        description: '验证 store 和 housing 的关联路径',
        detail: 'qft_joint_housing.store_id → qft_store\n确认可通过 store_id 关联',
        highlights: ['qft_store', 'qft_joint_housing'],
        highlightEdges: ['qft_joint_housing->qft_store'],
      },
      {
        title: '生成 SQL',
        description: '基于精简 Schema（2张表）生成查询',
        detail: 'SELECT COUNT(*) AS total\nFROM qft_joint_housing h\nJOIN qft_store s ON h.store_id = s.id\nWHERE s.name = \'城东门店\'\n  AND h.company_id = 1001\n  AND h.is_delete = 0',
        highlights: ['qft_store', 'qft_joint_housing'],
        highlightEdges: ['qft_joint_housing->qft_store'],
      },
    ],
  },
  {
    id: 'medium',
    question: '张三欠了多少钱？',
    difficulty: '中等',
    difficultyColor: '#f59e0b',
    description: '跨表查询 — 需要关联租客表和账单表',
    steps: [
      {
        title: '提取关键词',
        description: '识别人名和查询意图',
        detail: '• "张三" → 人名 → 搜索含 tenants_name 的表\n• "欠了多少钱" → 欠费 → 搜索含 debt_money 的列',
        highlights: ['qft_joint_tenants'],
        highlightEdges: [],
      },
      {
        title: '图谱定位租客表',
        description: '在 Schema Graph 中搜索包含 tenants_name 列的表',
        detail: 'Cypher: MATCH (t)-[:HAS_COLUMN]->(c)\n  WHERE c.column_name = "tenants_name"\n→ 命中: qft_joint_tenants, qft_whole_tenants\n\n同时搜索含 debt_money 的表:\n→ 命中: qft_joint_tenants_income',
        highlights: ['qft_joint_tenants', 'qft_whole_tenants', 'qft_joint_tenants_income'],
        highlightEdges: [],
      },
      {
        title: '图遍历找 JOIN 路径',
        description: '沿 REFERENCES 边发现关联关系',
        detail: 'qft_joint_tenants_income.tenants_id\n  → qft_joint_tenants\n\nJOIN 条件: tenants.id = income.tenants_id\n确认 income 表有 debt_money（欠费金额）列 ✓',
        highlights: ['qft_joint_tenants', 'qft_joint_tenants_income'],
        highlightEdges: ['qft_joint_tenants_income->qft_joint_tenants'],
      },
      {
        title: '精简 Schema → LLM',
        description: '只传 2 张表结构给 LLM（约 500 tokens，节省 95%）',
        detail: 'SELECT t.tenants_name,\n  SUM(i.debt_money) AS total_debt\nFROM qft_joint_tenants t\nJOIN qft_joint_tenants_income i\n  ON t.id = i.tenants_id\nWHERE t.tenants_name = \'张三\'\n  AND t.company_id = 1001\n  AND i.debt_money > 0\nGROUP BY t.tenants_name\n\n→ 结果: 张三 欠费 1,600 元',
        highlights: ['qft_joint_tenants', 'qft_joint_tenants_income'],
        highlightEdges: ['qft_joint_tenants_income->qft_joint_tenants'],
      },
    ],
  },
  {
    id: 'complex',
    question: '城西门店上月收入多少？分整租和合租列出',
    difficulty: '复杂',
    difficultyColor: '#ef4444',
    description: '跨模式 + 跨域查询 — 涉及门店、房源、账单、财务多表',
    steps: [
      {
        title: '提取关键词',
        description: '识别多个业务实体',
        detail: '• "城西门店" → qft_store（门店）\n• "上月收入" → qft_finance（财务流水，nature=1收入）\n• "整租和合租" → 需区分 business_type\n• "分...列出" → GROUP BY 分组',
        highlights: ['qft_store', 'qft_finance'],
        highlightEdges: [],
      },
      {
        title: '图遍历：门店 → 财务',
        description: '找到 store 和 finance 之间的关联路径',
        detail: 'qft_finance.store_id → qft_store\n\n1 跳直达，finance 表有:\n• store_id（门店关联）\n• nature（1=收入 2=支出）\n• business_type（2=整租 3=合租）\n• money（金额）\n• account_date（记账日期）',
        highlights: ['qft_store', 'qft_finance'],
        highlightEdges: ['qft_finance->qft_store'],
      },
      {
        title: '扩展遍历：验证完整链路',
        description: '检查是否需要更多表来满足查询',
        detail: '2 跳扩展:\nqft_finance → qft_whole_housing（整租房源）\nqft_finance → qft_joint_housing（合租房源）\nqft_finance → qft_whole_tenants（整租租客）\n\n本次查询只需 finance + store 即可，\n不需要关联房源/租客表',
        highlights: ['qft_store', 'qft_finance', 'qft_whole_housing', 'qft_joint_housing'],
        highlightEdges: ['qft_finance->qft_store', 'qft_finance->qft_whole_housing', 'qft_finance->qft_joint_housing'],
      },
      {
        title: '生成 SQL',
        description: '基于精简 Schema（2 张核心表）生成分组统计 SQL',
        detail: 'SELECT\n  CASE f.business_type\n    WHEN 2 THEN \'整租\'\n    WHEN 3 THEN \'合租\'\n    ELSE \'其他\'\n  END AS 业务模式,\n  SUM(f.money) AS 收入总额,\n  COUNT(*) AS 笔数\nFROM qft_finance f\nJOIN qft_store s ON f.store_id = s.id\nWHERE s.name = \'城西门店\'\n  AND f.nature = 1\n  AND f.company_id = 1001\n  AND DATE_FORMAT(f.account_date,\'%Y-%m\')\n    = DATE_FORMAT(DATE_SUB(NOW(),INTERVAL 1 MONTH),\'%Y-%m\')\nGROUP BY f.business_type',
        highlights: ['qft_store', 'qft_finance'],
        highlightEdges: ['qft_finance->qft_store'],
      },
    ],
  },
  {
    id: 'multi-hop',
    question: '哪些房间的电表余额不足 50 度？列出房间号和租客姓名',
    difficulty: '多跳',
    difficultyColor: '#d2a8ff',
    description: '3 跳关系查询 — 智能设备 → 房间 → 租客',
    steps: [
      {
        title: '提取关键词',
        description: '识别跨域查询意图',
        detail: '• "电表余额" → 智能设备域 → qft_smart_electricity_meter_*\n• "房间号" → 房间域 → qft_joint_room / qft_whole_room\n• "租客姓名" → 租客域 → qft_joint_tenants / qft_whole_tenants\n\n涉及 3 个业务域！',
        highlights: ['qft_smart_electricity_meter_recharge_record', 'qft_joint_room', 'qft_joint_tenants'],
        highlightEdges: [],
      },
      {
        title: '图遍历：3 跳关系链',
        description: '从电表记录沿边找到房间和租客',
        detail: '跳1: qft_smart_electricity_meter_recharge_record\n  .room_id → qft_joint_room\n\n跳2: qft_joint_room\n  .housing_id → qft_joint_housing\n\n跳3: qft_joint_tenants\n  .room_id → qft_joint_room（反向）\n\n完整链路:\n电表充值记录 → 房间 ← 租客',
        highlights: ['qft_smart_electricity_meter_recharge_record', 'qft_joint_room', 'qft_joint_tenants'],
        highlightEdges: ['qft_smart_electricity_meter_recharge_record->qft_joint_room', 'qft_joint_tenants->qft_joint_room'],
      },
      {
        title: '生成 SQL',
        description: '基于 3 张表的精简 Schema 生成多表 JOIN',
        detail: 'SELECT r.room_number AS 房间号,\n  t.tenants_name AS 租客,\n  e.balance AS 电表余额\nFROM qft_smart_electricity_meter_recharge_record e\nJOIN qft_joint_room r ON e.room_id = r.id\nJOIN qft_joint_tenants t ON t.room_id = r.id\nWHERE e.balance < 50\n  AND e.company_id = 1001\n  AND t.is_delete = 0\n  AND t.status = 1\nORDER BY e.balance ASC',
        highlights: ['qft_smart_electricity_meter_recharge_record', 'qft_joint_room', 'qft_joint_tenants'],
        highlightEdges: ['qft_smart_electricity_meter_recharge_record->qft_joint_room', 'qft_joint_tenants->qft_joint_room'],
      },
    ],
  },
]

export function TraversalDemo() {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const nodesDataRef = useRef<DataSet<Record<string, unknown>> | null>(null)
  const edgesDataRef = useRef<DataSet<Record<string, unknown>> | null>(null)

  const [selectedTable, setSelectedTable] = useState('')
  const [traversalResult, setTraversalResult] = useState<{ hop1: string[]; hop2: string[] } | null>(null)
  const [activeScenario, setActiveScenario] = useState<string | null>(null)
  const [storyStep, setStoryStep] = useState(-1)

  const dedupedEdges = useMemo(() => deduplicateEdges(graphData.edges), [])

  const edgeKeyToId = useMemo(() => {
    const map = new Map<string, string>()
    dedupedEdges.forEach((e, i) => map.set(`${e.source}->${e.target}`, `e${i}`))
    return map
  }, [dedupedEdges])

  // 初始化 vis-network
  useEffect(() => {
    if (!containerRef.current) return

    const nodesData = new DataSet(
      graphData.nodes.map(n => ({
        id: n.name,
        label: n.name.replace('qft_', '').replace('smart_electricity_meter_', 'meter_'),
        color: { background: DOMAIN_COLORS[n.domain] || '#8b949e', border: DOMAIN_COLORS[n.domain] || '#8b949e' },
        size: Math.max(10, Math.min(35, n.col_count / 3)),
        font: { color: '#e6edf3', size: 9, face: 'system-ui' },
        borderWidth: 2,
        shape: 'dot',
      }))
    )

    const edgesData = new DataSet(
      dedupedEdges.map((e, i) => ({
        id: `e${i}`,
        from: e.source,
        to: e.target,
        arrows: 'to',
        color: { color: '#30363d' },
        width: 1,
        smooth: { enabled: true, type: 'curvedCW', roundness: 0.15 },
      }))
    )

    nodesDataRef.current = nodesData
    edgesDataRef.current = edgesData

    const network = new Network(containerRef.current, { nodes: nodesData, edges: edgesData }, {
      physics: {
        barnesHut: { gravitationalConstant: -2500, springLength: 160, damping: 0.3 },
        stabilization: { iterations: 150 },
      },
      interaction: { hover: true, tooltipDelay: 100 },
    })

    networkRef.current = network
    return () => network.destroy()
  }, [dedupedEdges])

  const resetAll = useCallback(() => {
    const nd = nodesDataRef.current, ed = edgesDataRef.current
    if (!nd || !ed) return
    graphData.nodes.forEach(n => {
      nd.update({ id: n.name, color: { background: DOMAIN_COLORS[n.domain] || '#8b949e', border: DOMAIN_COLORS[n.domain] || '#8b949e' }, font: { color: '#e6edf3', size: 9 }, borderWidth: 2, size: Math.max(10, Math.min(35, n.col_count / 3)) } as Record<string, unknown>)
    })
    dedupedEdges.forEach((_, i) => {
      ed.update({ id: `e${i}`, color: { color: '#30363d' }, width: 1 })
    })
  }, [dedupedEdges])

  const highlight = useCallback((activeNodes: Set<string>, activeEdgeKeys: string[], focusNode?: string) => {
    const nd = nodesDataRef.current, ed = edgesDataRef.current
    if (!nd || !ed) return

    graphData.nodes.forEach(n => {
      if (activeNodes.has(n.name)) {
        nd.update({ id: n.name, color: { background: '#1f6feb', border: '#58a6ff' }, font: { color: '#fff', size: 11 }, borderWidth: 3, size: Math.max(18, Math.min(40, n.col_count / 2.5)) } as Record<string, unknown>)
      } else {
        nd.update({ id: n.name, color: { background: '#161b22', border: '#21262d' }, font: { color: '#30363d', size: 9 }, borderWidth: 1, size: Math.max(8, Math.min(25, n.col_count / 4)) } as Record<string, unknown>)
      }
    })

    const highlightedIds = new Set(activeEdgeKeys.map(k => edgeKeyToId.get(k)).filter(Boolean))
    dedupedEdges.forEach((_, i) => {
      const eid = `e${i}`
      if (highlightedIds.has(eid)) {
        ed.update({ id: eid, color: { color: '#58a6ff' }, width: 3 })
      } else {
        ed.update({ id: eid, color: { color: 'rgba(48,54,61,0.15)' }, width: 0.5 })
      }
    })

    if (focusNode) networkRef.current?.focus(focusNode, { scale: 1.3, animation: true })
  }, [dedupedEdges, edgeKeyToId])

  // 关系网络遍历
  const handleTraverse = useCallback(() => {
    if (!selectedTable) return
    setActiveScenario(null)
    setStoryStep(-1)
    resetAll()
    const { hop1, hop2 } = computeHops(selectedTable)
    setTraversalResult({ hop1: [...hop1], hop2: [...hop2] })

    const nd = nodesDataRef.current, ed = edgesDataRef.current
    if (!nd || !ed) return
    graphData.nodes.forEach(n => {
      let bg = '#161b22', bd = '#21262d', fc = '#30363d', sz = 8
      if (n.name === selectedTable) { bg = '#f59e0b'; bd = '#f59e0b'; fc = '#fff'; sz = 30 }
      else if (hop1.has(n.name)) { bg = '#1f6feb'; bd = '#58a6ff'; fc = '#fff'; sz = 20 }
      else if (hop2.has(n.name)) { bg = '#8b5cf6'; bd = '#a78bfa'; fc = '#e6edf3'; sz = 15 }
      nd.update({ id: n.name, color: { background: bg, border: bd }, font: { color: fc, size: sz > 15 ? 11 : 9 }, borderWidth: n.name === selectedTable ? 4 : 2, size: sz } as Record<string, unknown>)
    })
    const involved = new Set([selectedTable, ...hop1])
    dedupedEdges.forEach((e, i) => {
      const active = involved.has(e.source) && involved.has(e.target)
      ed.update({ id: `e${i}`, color: { color: active ? '#58a6ff' : 'rgba(48,54,61,0.1)' }, width: active ? 2.5 : 0.5 })
    })
    networkRef.current?.focus(selectedTable, { scale: 1.0, animation: true })
  }, [selectedTable, resetAll, dedupedEdges])

  // 场景演示
  const currentScenario = SCENARIOS.find(s => s.id === activeScenario)

  const startScenario = useCallback((id: string) => {
    setActiveScenario(id)
    setStoryStep(0)
    setTraversalResult(null)
    setSelectedTable('')
    const scenario = SCENARIOS.find(s => s.id === id)
    if (!scenario) return
    const step = scenario.steps[0]
    resetAll()
    setTimeout(() => {
      highlight(new Set(step.highlights), step.highlightEdges, step.highlights[0])
    }, 100)
  }, [resetAll, highlight])

  const nextStep = useCallback(() => {
    if (!currentScenario) return
    const next = storyStep + 1
    if (next >= currentScenario.steps.length) return
    setStoryStep(next)
    const step = currentScenario.steps[next]
    highlight(new Set(step.highlights), step.highlightEdges, step.highlights[0])
  }, [storyStep, currentScenario, highlight])

  return (
    <div style={{ height: 'calc(100vh - 48px)', display: 'flex', overflow: 'hidden' }}>
      {/* 左：图谱 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ padding: '6px 12px', background: '#161b22', borderBottom: '1px solid #30363d', fontSize: 12, color: '#8b949e', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>图谱遍历视图 — 高亮节点为当前步骤涉及的表</span>
          <button onClick={() => { resetAll(); networkRef.current?.fit({ animation: true }) }} style={{ background: '#21262d', border: '1px solid #30363d', color: '#8b949e', padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 11 }}>重置</button>
        </div>
        <div ref={containerRef} style={{ flex: 1, minHeight: 400, background: '#0d1117' }} />
        <div style={{ display: 'flex', gap: 12, padding: '4px 12px', background: '#161b22', borderTop: '1px solid #30363d', fontSize: 10, color: '#8b949e', flexWrap: 'wrap' }}>
          {DOMAINS.map(d => (
            <span key={d} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: DOMAIN_COLORS[d], display: 'inline-block' }} />{d}
            </span>
          ))}
          <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: '50%', background: '#1f6feb', display: 'inline-block' }} />高亮节点</span>
        </div>
      </div>

      {/* 右：控制面板 */}
      <div style={{ width: 420, borderLeft: '1px solid #30363d', background: '#161b22', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #30363d', fontSize: 14, fontWeight: 600 }}>
          遍历控制面板
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>

          {/* 场景选择 */}
          <div style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
            业务场景演示
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 20 }}>
            {SCENARIOS.map(s => (
              <button key={s.id} onClick={() => startScenario(s.id)} style={{
                textAlign: 'left', padding: '10px 12px', background: activeScenario === s.id ? 'rgba(88,166,255,0.1)' : '#0d1117',
                border: `1px solid ${activeScenario === s.id ? '#58a6ff' : '#21262d'}`,
                borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ padding: '1px 8px', borderRadius: 10, fontSize: 10, fontWeight: 600, background: s.difficultyColor + '22', color: s.difficultyColor }}>{s.difficulty}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#e6edf3' }}>{s.question}</span>
                </div>
                <div style={{ fontSize: 11, color: '#8b949e', paddingLeft: 0 }}>{s.description}</div>
              </button>
            ))}
          </div>

          {/* 场景步骤 */}
          {currentScenario && storyStep >= 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
                {currentScenario.question}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {currentScenario.steps.map((step, idx) => {
                  const isCurrent = idx === storyStep
                  const isPast = idx < storyStep
                  const isFuture = idx > storyStep
                  return (
                    <div key={idx} style={{
                      background: isCurrent ? 'rgba(88,166,255,0.08)' : '#0d1117',
                      border: `1px solid ${isCurrent ? '#58a6ff' : '#21262d'}`,
                      borderRadius: 8, padding: 10, opacity: isFuture ? 0.35 : 1, transition: 'all 0.3s',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: (isCurrent || isPast) ? 6 : 0 }}>
                        <div style={{
                          width: 20, height: 20, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          background: isPast ? '#7ee787' : isCurrent ? '#58a6ff' : '#30363d',
                          color: (isPast || isCurrent) ? '#0d1117' : '#8b949e', fontSize: 10, fontWeight: 700, flexShrink: 0,
                        }}>
                          {isPast ? '✓' : idx + 1}
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: isCurrent ? '#58a6ff' : isPast ? '#7ee787' : '#8b949e' }}>
                          {step.title}
                        </span>
                      </div>
                      {(isCurrent || isPast) && (
                        <>
                          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, paddingLeft: 26 }}>{step.description}</div>
                          <pre style={{ fontSize: 11, marginLeft: 26, padding: '6px 10px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#21262d', borderRadius: 6, color: '#79c0ff' }}>
                            {step.detail}
                          </pre>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                {storyStep < currentScenario.steps.length - 1 ? (
                  <button onClick={nextStep} style={{ flex: 1, padding: '8px', background: '#1f6feb', color: '#fff', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                    下一步 ({storyStep + 2}/{currentScenario.steps.length})
                  </button>
                ) : (
                  <div style={{ flex: 1, padding: '10px', background: 'rgba(126,231,135,0.1)', border: '1px solid rgba(126,231,135,0.3)', borderRadius: 8, textAlign: 'center' }}>
                    <span style={{ color: '#7ee787', fontSize: 12, fontWeight: 600 }}>✓ 查询完成</span>
                    <div style={{ fontSize: 11, color: '#8b949e', marginTop: 2 }}>
                      图遍历帮助 AI 从 77 张表中定位到 {currentScenario.steps[currentScenario.steps.length - 1].highlights.length} 张
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 分割线 */}
          <div style={{ borderTop: '1px solid #21262d', margin: '12px 0' }} />

          {/* 手动遍历 */}
          <div style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
            手动探索
          </div>
          <select value={selectedTable} onChange={e => setSelectedTable(e.target.value)} style={{
            width: '100%', padding: '7px 10px', background: '#0d1117', border: '1px solid #30363d', borderRadius: 6, color: '#e6edf3', fontSize: 12, marginBottom: 6,
          }}>
            <option value="">选择任意表...</option>
            {[...graphData.nodes].sort((a, b) => a.domain.localeCompare(b.domain)).map(n => (
              <option key={n.name} value={n.name}>{n.name} ({n.domain})</option>
            ))}
          </select>
          <button onClick={handleTraverse} disabled={!selectedTable} style={{
            width: '100%', padding: '7px', background: selectedTable ? '#58a6ff' : '#21262d', color: selectedTable ? '#0d1117' : '#8b949e',
            border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: selectedTable ? 'pointer' : 'default',
          }}>
            查看关系网络
          </button>

          {traversalResult && (
            <div style={{ background: '#0d1117', border: '1px solid #21262d', borderRadius: 8, padding: 10, marginTop: 8 }}>
              <div style={{ fontSize: 11, marginBottom: 6 }}>
                <span style={{ color: '#f59e0b' }}>● 起始</span>: {selectedTable}
              </div>
              <div style={{ fontSize: 11, marginBottom: 4 }}>
                <span style={{ color: '#58a6ff' }}>● 1跳</span> ({traversalResult.hop1.length}):
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 3 }}>
                  {traversalResult.hop1.map(t => <code key={t} style={{ fontSize: 10 }}>{t.replace('qft_', '')}</code>)}
                </div>
              </div>
              <div style={{ fontSize: 11 }}>
                <span style={{ color: '#8b5cf6' }}>● 2跳</span> ({traversalResult.hop2.length}):
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 3 }}>
                  {traversalResult.hop2.map(t => <code key={t} style={{ fontSize: 10 }}>{t.replace('qft_', '')}</code>)}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
