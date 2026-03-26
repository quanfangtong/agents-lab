/**
 * Benchmark 结果 Tab：核心表 vs 噪音表全面对比 + 每题 SQL 详情
 */
import { useState } from 'react'

import rawComparison from '../data/benchmarkComparison.json'
const data = rawComparison as any

const COLORS: Record<string, string> = {
  'A_Text2SQL': '#8b949e',
  'B_Kuzu': '#10b981',
  'C_Neo4j': '#3b82f6',
  'D_FalkorDB': '#f59e0b',
}
const LABELS: Record<string, string> = {
  'A_Text2SQL': 'A. Text2SQL',
  'B_Kuzu': 'B. Kuzu',
  'C_Neo4j': 'C. Neo4j',
  'D_FalkorDB': 'D. FalkorDB',
}
const SOLS = ['A_Text2SQL', 'B_Kuzu', 'C_Neo4j', 'D_FalkorDB']
const model = data.model

function pct(n: number, d: number) { return d ? (n / d * 100) : 0 }
function pctStr(n: number, d: number) { return d ? `${(n / d * 100).toFixed(1)}%` : '-' }
function getStats(scenario: any, sol: string) { return scenario?.results?.[sol]?.[model] }

const statusIcon = (q: any) => {
  if (!q) return { bg: '#21262d', fg: '#6e7681', icon: '-', label: '无数据' }
  if (q.verified) return { bg: '#7ee78733', fg: '#7ee787', icon: '✓', label: '正确' }
  if (q.sql_ok) return { bg: '#f0883e22', fg: '#f0883e', icon: '~', label: 'SQL可执行但结果不对' }
  return { bg: '#ff7b7222', fg: '#ff7b72', icon: '✗', label: '失败' }
}

// ============ Hero ============

function HeroInsight() {
  const s0 = data.scenarios[0], s1 = data.scenarios[1]
  const a0 = getStats(s0, 'A_Text2SQL'), a1 = getStats(s1, 'A_Text2SQL')
  const best1 = SOLS.reduce((best, sol) => {
    const s = getStats(s1, sol)
    return s && s.verified > (getStats(s1, best)?.verified || 0) ? sol : best
  }, SOLS[0])
  const bestStats = getStats(s1, best1)

  return (
    <div style={{ background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)', border: '1px solid #30363d', borderRadius: 12, padding: 28, marginBottom: 28 }}>
      <div style={{ fontSize: 13, color: '#58a6ff', fontWeight: 600, letterSpacing: 1, marginBottom: 8 }}>KEY FINDING</div>
      <h2 style={{ fontSize: 22, lineHeight: 1.4, margin: '0 0 16px', color: '#e6edf3' }}>
        噪音表使 Text2SQL 准确率下降 {a0 && a1 ? (pct(a1.verified, a1.total) - pct(a0.verified, a0.total)).toFixed(1) : '?'}%，
        图谱方案不受影响
      </h2>
      <p style={{ color: '#8b949e', fontSize: 14, lineHeight: 1.7, margin: 0 }}>
        在 207 张表的生产模拟环境下，Text2SQL 需要处理 ~48K tokens 的 schema 上下文，准确率从 {a0 ? pctStr(a0.verified, a0.total) : '?'} 降至 {a1 ? pctStr(a1.verified, a1.total) : '?'}。
        而图谱方案通过知识图谱精准定位相关表（~11K tokens），{LABELS[best1]} 达到 {bestStats ? pctStr(bestStats.verified, bestStats.total) : '?'} 的最高准确率，
        比 Text2SQL 高出 {bestStats && a1 ? (pct(bestStats.verified, bestStats.total) - pct(a1.verified, a1.total)).toFixed(1) : '?'} 个百分点。
      </p>
    </div>
  )
}

// ============ Overview Cards ============

function OverviewCards() {
  const s0 = data.scenarios[0], s1 = data.scenarios[1]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
      {SOLS.map(sol => {
        const c = getStats(s0, sol), n = getStats(s1, sol)
        const cPct = c ? pct(c.verified, c.total) : 0
        const nPct = n ? pct(n.verified, n.total) : 0
        const delta = nPct - cPct
        return (
          <div key={sol} style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 10, padding: 18, position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: COLORS[sol] }} />
            <div style={{ fontSize: 13, color: COLORS[sol], fontWeight: 700, marginBottom: 12 }}>{LABELS[sol]}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4 }}>
              <span style={{ fontSize: 32, fontWeight: 800, color: '#e6edf3' }}>{nPct.toFixed(0)}</span>
              <span style={{ fontSize: 16, color: '#8b949e' }}>%</span>
              <span style={{ fontSize: 13, fontWeight: 700, marginLeft: 'auto', color: delta > 0 ? '#7ee787' : delta < -1 ? '#ff7b72' : '#8b949e' }}>
                {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
              </span>
            </div>
            <div style={{ fontSize: 11, color: '#8b949e' }}>207 表场景 EX 准确率</div>
            <div style={{ display: 'flex', gap: 4, marginTop: 10 }}>
              <div style={{ flex: 1, height: 6, borderRadius: 3, overflow: 'hidden', background: '#21262d' }}>
                <div style={{ height: '100%', width: `${cPct}%`, background: `${COLORS[sol]}66`, borderRadius: 3 }} />
              </div>
              <div style={{ flex: 1, height: 6, borderRadius: 3, overflow: 'hidden', background: '#21262d' }}>
                <div style={{ height: '100%', width: `${nPct}%`, background: COLORS[sol], borderRadius: 3 }} />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#8b949e', marginTop: 4 }}>
              <span>77 表: {cPct.toFixed(0)}%</span>
              <span>207 表: {nPct.toFixed(0)}%</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ============ Comparison Table ============

function ComparisonTable() {
  const s0 = data.scenarios[0], s1 = data.scenarios[1]
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 16, marginBottom: 12 }}>详细指标对比</h3>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #30363d' }}>
              <th style={{ padding: '10px 12px', textAlign: 'left', color: '#8b949e' }}>方案</th>
              <th style={{ padding: '10px 8px', textAlign: 'center', color: '#8b949e' }} colSpan={3}>77 表（核心）</th>
              <th style={{ padding: '10px 8px', textAlign: 'center', color: '#8b949e', borderLeft: '2px solid #30363d' }} colSpan={3}>207 表（+噪音）</th>
              <th style={{ padding: '10px 8px', textAlign: 'center', color: '#f0883e', borderLeft: '2px solid #30363d' }}>EX 变化</th>
            </tr>
            <tr style={{ borderBottom: '1px solid #21262d' }}>
              <th></th>
              {['SQL可执行', 'EX准确率', 'Token'].map(h => <th key={`a-${h}`} style={{ padding: '4px 8px', textAlign: 'right', color: '#6e7681', fontSize: 11 }}>{h}</th>)}
              {['SQL可执行', 'EX准确率', 'Token'].map(h => <th key={`b-${h}`} style={{ padding: '4px 8px', textAlign: 'right', color: '#6e7681', fontSize: 11, borderLeft: h === 'SQL可执行' ? '2px solid #30363d' : 'none' }}>{h}</th>)}
              <th style={{ borderLeft: '2px solid #30363d' }}></th>
            </tr>
          </thead>
          <tbody>
            {SOLS.map(sol => {
              const c = getStats(s0, sol), n = getStats(s1, sol)
              const cEx = c ? pct(c.verified, c.total) : 0
              const nEx = n ? pct(n.verified, n.total) : 0
              const delta = nEx - cEx
              return (
                <tr key={sol} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={{ padding: '10px 12px', color: COLORS[sol], fontWeight: 700 }}>{LABELS[sol]}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right' }}>{c?.sql_ok_rate || '-'}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 700 }}>{c?.verified_rate || '-'}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', color: '#8b949e' }}>~{c ? (c.avg_tokens / 1000).toFixed(0) : '?'}K</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', borderLeft: '2px solid #30363d' }}>{n?.sql_ok_rate || '-'}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 700 }}>{n?.verified_rate || '-'}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', color: '#8b949e' }}>~{n ? (n.avg_tokens / 1000).toFixed(0) : '?'}K</td>
                  <td style={{ padding: '10px 8px', textAlign: 'center', fontWeight: 800, fontSize: 14, borderLeft: '2px solid #30363d', color: delta > 1 ? '#7ee787' : delta < -1 ? '#ff7b72' : '#8b949e' }}>
                    {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ============ Category + Difficulty ============

function CategoryBreakdown() {
  const s1 = data.scenarios[1]
  const categories = ['accuracy', 'basic_analysis', 'advanced_analysis']
  const catLabels: Record<string, string> = { accuracy: '精确查询', basic_analysis: '基础分析', advanced_analysis: '高级分析' }
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 16, marginBottom: 12 }}>按题目类别拆分（207 表场景）</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {categories.map(cat => (
          <div key={cat} style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e6edf3', marginBottom: 10 }}>{catLabels[cat]}</div>
            {SOLS.map(sol => {
              const st = s1.by_category?.[cat]?.[sol]
              if (!st) return null
              const p = pct(st.verified, st.total)
              return (
                <div key={sol} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: COLORS[sol], fontWeight: 600, width: 65, flexShrink: 0 }}>{LABELS[sol].split('. ')[1]}</span>
                  <div style={{ flex: 1, height: 14, background: '#21262d', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${p}%`, background: COLORS[sol], borderRadius: 3, minWidth: p > 0 ? 2 : 0 }} />
                  </div>
                  <span style={{ fontSize: 11, color: '#8b949e', width: 50, textAlign: 'right' }}>{st.verified}/{st.total}</span>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function DifficultyBreakdown() {
  const s1 = data.scenarios[1]
  const diffs = ['easy', 'medium', 'hard', 'expert']
  const diffLabels: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难', expert: '专家' }
  const diffColors: Record<string, string> = { easy: '#7ee787', medium: '#f0883e', hard: '#ff7b72', expert: '#bc8cff' }
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 16, marginBottom: 12 }}>按难度拆分（207 表场景）</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #30363d' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', color: '#8b949e' }}>难度</th>
            {SOLS.map(sol => <th key={sol} style={{ padding: '8px 12px', textAlign: 'center', color: COLORS[sol], fontWeight: 600 }}>{LABELS[sol].split('. ')[1]}</th>)}
          </tr>
        </thead>
        <tbody>
          {diffs.map(d => {
            const has = SOLS.some(sol => s1.by_difficulty?.[d]?.[sol])
            if (!has) return null
            return (
              <tr key={d} style={{ borderBottom: '1px solid #21262d' }}>
                <td style={{ padding: '8px 12px', color: diffColors[d], fontWeight: 600 }}>{diffLabels[d]}</td>
                {SOLS.map(sol => {
                  const st = s1.by_difficulty?.[d]?.[sol]
                  if (!st) return <td key={sol} style={{ textAlign: 'center', color: '#6e7681' }}>-</td>
                  const p = pct(st.verified, st.total)
                  return <td key={sol} style={{ padding: '8px 12px', textAlign: 'center' }}>
                    <span style={{ fontWeight: 700, color: p >= 60 ? '#7ee787' : p >= 40 ? '#f0883e' : '#ff7b72' }}>{p.toFixed(0)}%</span>
                    <span style={{ color: '#6e7681', fontSize: 11 }}> ({st.verified}/{st.total})</span>
                  </td>
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ============ Per-Question Detail (with SQL) ============

function QuestionDetail() {
  const [scenario, setScenario] = useState<0 | 1>(1)
  const [expandedQ, setExpandedQ] = useState<string | null>(null)
  const s = data.scenarios[scenario]
  const qMeta = data.question_meta || {}
  const qids = Object.keys(qMeta).sort()
  const diffColors: Record<string, string> = { easy: '#7ee787', medium: '#f0883e', hard: '#ff7b72', expert: '#bc8cff' }

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <h3 style={{ fontSize: 16, margin: 0 }}>每题详细结果</h3>
        <div style={{ display: 'flex', gap: 4 }}>
          {[0, 1].map(i => (
            <button key={i} onClick={() => setScenario(i as 0 | 1)} style={{
              padding: '3px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', fontSize: 11,
              background: scenario === i ? '#238636' : '#21262d', color: scenario === i ? '#fff' : '#8b949e',
            }}>{data.scenarios[i].label}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, fontSize: 11, color: '#8b949e' }}>
          <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: '#7ee787', marginRight: 3, verticalAlign: 'middle' }} />正确</span>
          <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: '#f0883e', marginRight: 3, verticalAlign: 'middle' }} />SQL可执行</span>
          <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: '#ff7b72', marginRight: 3, verticalAlign: 'middle' }} />失败</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {qids.map(qid => {
          const meta = qMeta[qid]
          const qData = s.questions?.[qid] || {}
          const isExpanded = expandedQ === qid

          return (
            <div key={qid} style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 6, overflow: 'hidden' }}>
              {/* Collapsed row */}
              <div onClick={() => setExpandedQ(isExpanded ? null : qid)} style={{
                padding: '8px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                background: isExpanded ? '#1c2333' : 'transparent',
              }}>
                <span style={{ color: '#6e7681', fontSize: 11, minWidth: 32, fontFamily: 'monospace' }}>{qid}</span>
                <span style={{ fontSize: 10, color: diffColors[meta?.difficulty] || '#8b949e', minWidth: 30 }}>{meta?.difficulty}</span>
                <span style={{ fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{meta?.question}</span>
                <div style={{ display: 'flex', gap: 3, flexShrink: 0 }}>
                  {SOLS.map(sol => {
                    const st = statusIcon(qData[sol])
                    return <span key={sol} style={{
                      width: 20, height: 20, borderRadius: 3, fontSize: 11, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: st.bg, color: st.fg,
                    }}>{st.icon}</span>
                  })}
                </div>
                <span style={{ color: '#6e7681', fontSize: 11, flexShrink: 0 }}>{isExpanded ? '▲' : '▼'}</span>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div style={{ padding: '0 12px 12px', borderTop: '1px solid #21262d' }}>
                  {meta?.expected_tables?.length > 0 && (
                    <div style={{ padding: '8px 0', fontSize: 11, color: '#8b949e' }}>
                      期望表: {meta.expected_tables.join(', ')}
                    </div>
                  )}

                  {SOLS.map(sol => {
                    const q = qData[sol]
                    if (!q) return null
                    const st = statusIcon(q)
                    return (
                      <div key={sol} style={{
                        marginTop: 8, padding: 12, background: '#0d1117', borderRadius: 6,
                        border: `1px solid ${q.verified ? '#21262d' : q.sql_ok ? '#f0883e33' : '#ff7b7233'}`,
                      }}>
                        {/* Header */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                          <span style={{ color: COLORS[sol], fontWeight: 700, fontSize: 13 }}>{LABELS[sol]}</span>
                          <span style={{
                            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                            background: st.bg, color: st.fg,
                          }}>{st.label}</span>
                          {q.match_detail && <span style={{ fontSize: 11, color: '#8b949e' }}>{q.match_detail}</span>}
                          <span style={{ fontSize: 11, color: '#6e7681', marginLeft: 'auto' }}>
                            {q.total_ms}ms | {q.tables} 表 | ~{q.tokens} tokens
                          </span>
                        </div>

                        {/* Step timing */}
                        {(q.step1_ms != null || q.step2_ms != null || q.step3_ms != null) && (
                          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#6e7681', marginBottom: 8 }}>
                            {q.step1_ms != null && <span>意图分析: {q.step1_ms}ms</span>}
                            {q.step2_ms != null && <span>Schema获取: {q.step2_ms}ms</span>}
                            {q.step3_ms != null && <span>SQL生成: {q.step3_ms}ms</span>}
                            {q.step4_ms != null && <span>执行: {q.step4_ms}ms</span>}
                          </div>
                        )}

                        {/* Intent keywords */}
                        {q.step1_intent?.search_keywords && (
                          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 6 }}>
                            搜索关键词: <span style={{ color: '#58a6ff' }}>{q.step1_intent.search_keywords.join(', ')}</span>
                          </div>
                        )}

                        {/* Table recall */}
                        {q.table_recall != null && (
                          <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 6 }}>
                            表召回率: <span style={{ color: q.table_recall >= 0.8 ? '#7ee787' : q.table_recall >= 0.5 ? '#f0883e' : '#ff7b72', fontWeight: 600 }}>
                              {(q.table_recall * 100).toFixed(0)}%
                            </span>
                            {q.expected_tables?.length > 0 && <span> (期望: {q.expected_tables.join(', ')})</span>}
                          </div>
                        )}

                        {/* Selected tables */}
                        {q.table_names?.length > 0 && q.table_names.length < 77 && (
                          <details style={{ fontSize: 11, color: '#6e7681', marginBottom: 6 }}>
                            <summary style={{ cursor: 'pointer' }}>选中的表 ({q.table_names.length} 张)</summary>
                            <div style={{ padding: '4px 0', lineHeight: 1.6 }}>{q.table_names.join(', ')}</div>
                          </details>
                        )}

                        {/* Generated SQL */}
                        <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4 }}>生成的 SQL:</div>
                        <pre style={{
                          fontSize: 11, padding: 10, background: '#161b22', borderRadius: 4,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.5,
                          color: q.verified ? '#79c0ff' : q.sql_ok ? '#f0883e' : '#ff7b72',
                          maxHeight: 300, overflow: 'auto', margin: '0 0 6px',
                          border: '1px solid #21262d',
                        }}>
                          {q.generated_sql || 'N/A'}
                        </pre>

                        {/* Error */}
                        {q.error && (
                          <div style={{ fontSize: 11, color: '#ff7b72', padding: '6px 10px', background: '#ff7b7211', borderRadius: 4, marginBottom: 6, wordBreak: 'break-all' }}>
                            {q.error}
                          </div>
                        )}

                        {/* Execution result */}
                        {q.sql_ok && q.execution_result && q.execution_result.length > 0 && (
                          <div style={{ marginTop: 4 }}>
                            <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4 }}>
                              执行结果 ({q.row_count} 行{q.row_count > 5 ? '，显示前 5' : ''}):
                            </div>
                            <div style={{ overflowX: 'auto' }}>
                              <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
                                <thead>
                                  <tr style={{ borderBottom: '1px solid #21262d' }}>
                                    {Object.keys(q.execution_result[0]).map((k: string) => (
                                      <th key={k} style={{ padding: '4px 8px', textAlign: 'left', color: '#8b949e', whiteSpace: 'nowrap' }}>{k}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {q.execution_result.map((row: any, i: number) => (
                                    <tr key={i} style={{ borderBottom: '1px solid #161b22' }}>
                                      {Object.values(row).map((v: any, j: number) => (
                                        <td key={j} style={{ padding: '4px 8px', color: '#c9d1d9', whiteSpace: 'nowrap', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                          {v == null ? <span style={{ color: '#6e7681' }}>NULL</span> : String(v)}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============ Insights ============

function Insights() {
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 16, marginBottom: 12, color: '#58a6ff' }}>分析与洞见</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {[
          { title: '噪音表对 Text2SQL 的影响机制', color: '#ff7b72',
            content: 'Text2SQL 将全部 207 张表的 schema 塞入 prompt（~48K tokens），LLM 需要在大量相似表名中找到正确的表。例如 qft_arrears_record（噪音）和 qft_joint_tenants_income（核心）功能相似但结构不同，LLM 容易混淆。' },
          { title: '图谱方案的抗噪声能力', color: '#7ee787',
            content: '图谱方案通过 LLM 意图分析提取搜索关键词，在知识图谱中精准定位相关表。噪音表不在图谱中，天然被过滤。即使加入 130 张噪音表，图谱方案的 token 用量稳定在 ~11K，上下文不被污染。' },
          { title: 'SQL 可执行率 vs 结果正确率', color: '#f0883e',
            content: '图谱方案的 SQL 可执行率（89-97%）远高于 Text2SQL（57%）。但可执行不等于正确——部分 SQL 能跑但结果偏差，说明表选对了但 SQL 逻辑仍有改进空间（如聚合方式、过滤条件）。' },
          { title: '业务模式补全的关键作用', color: '#bc8cff',
            content: '全房通有三种平行业务模式（整租/合租/集中式），许多查询需要跨模式 UNION ALL。图谱方案的「业务模式自动补全」确保找到一种模式的表后，自动补全其他模式的对应表，这是准确率提升的核心因素。' },
          { title: 'FalkorDB 为何表现最优', color: '#f59e0b',
            content: 'FalkorDB 在两个场景下都取得最高准确率（56.8% → 62.2%）。其基于 Redis 协议的图查询在表搜索和 JOIN 路径发现上响应快且稳定，高并发场景下连接可靠性更好。' },
          { title: '生产环境部署建议', color: '#58a6ff',
            content: '真实 SaaS 数据库通常有数百甚至数千张表。本实验证明，随着表数量增加，直接 Text2SQL 的准确率会持续下降，而图谱增强方案能保持稳定。建议在生产环境中采用图谱方案作为 Schema 选择层。' },
        ].map((insight, i) => (
          <div key={i} style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 18 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: insight.color, marginBottom: 8 }}>{insight.title}</div>
            <p style={{ fontSize: 13, color: '#c9d1d9', lineHeight: 1.7, margin: 0 }}>{insight.content}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ============ Methodology ============

function Methodology() {
  return (
    <div style={{ lineHeight: 1.8, fontSize: 14, color: '#c9d1d9' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 20 }}>
          <h4 style={{ color: '#58a6ff', marginBottom: 10 }}>实验条件</h4>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <tbody>
              {[
                ['模型', 'GPT-5.4 (Azure, reasoning=high)'],
                ['测试集', '37 道确定性问题（真实 PM 查询场景）'],
                ['验证', 'Golden Answer 对比（expected_sql 执行结果）'],
                ['自纠错', '关闭（测试首次生成质量）'],
                ['Schema', '统一轻量格式（表名+注释+列名列表）'],
                ['并发', '5 路并行，429 自动重试'],
              ].map(([k, v]) => (
                <tr key={k} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={{ padding: 6, color: '#8b949e', width: 70 }}>{k}</td>
                  <td style={{ padding: 6 }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 20 }}>
          <h4 style={{ color: '#58a6ff', marginBottom: 10 }}>两组对比</h4>
          <div style={{ padding: 12, background: '#0d1117', borderRadius: 6, marginBottom: 10 }}>
            <div style={{ color: '#7ee787', fontWeight: 600, marginBottom: 4 }}>场景 A：核心表 (77张)</div>
            <p style={{ fontSize: 12, color: '#8b949e', margin: 0 }}>仅业务核心表，测试基础能力</p>
          </div>
          <div style={{ padding: 12, background: '#0d1117', borderRadius: 6 }}>
            <div style={{ color: '#f0883e', fontWeight: 600, marginBottom: 4 }}>场景 B：生产模拟 (207张)</div>
            <p style={{ fontSize: 12, color: '#8b949e', margin: 0 }}>+130 张从生产库提取的真实噪音表（审批、日志、归档、代理等）</p>
          </div>
        </div>
      </div>
      <div style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 20 }}>
        <h4 style={{ color: '#58a6ff', marginBottom: 10 }}>四个方案的 Pipeline</h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 3fr', gap: 0, fontSize: 13 }}>
          {SOLS.map(sol => (
            <div key={sol} style={{ display: 'contents' }}>
              <div style={{ padding: '10px 12px', borderBottom: '1px solid #21262d', color: COLORS[sol], fontWeight: 700 }}>{LABELS[sol]}</div>
              <div style={{ padding: '10px 12px', borderBottom: '1px solid #21262d', color: '#8b949e' }}>
                {sol === 'A_Text2SQL'
                  ? <>全部表 Schema → <span style={{ color: '#e6edf3' }}>LLM 生成 SQL</span> → 执行</>
                  : <><span style={{ color: '#e6edf3' }}>LLM 意图分析</span> → 图谱搜索 + 模式补全 → 精选表 Schema + JOIN 路径 → <span style={{ color: '#e6edf3' }}>LLM 生成 SQL</span> → 执行</>
                }
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ============ Main ============

export function BenchmarkResults() {
  const [tab, setTab] = useState<'results' | 'details' | 'questions' | 'methodology'>('results')

  const hasData = data.scenarios?.some((s: any) => Object.keys(s.results || {}).length > 0)
  if (!hasData) return <div style={{ padding: 40, textAlign: 'center', color: '#8b949e' }}>Benchmark 数据未就绪</div>

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {[
          { key: 'results' as const, label: '对比总览' },
          { key: 'details' as const, label: '分类分析' },
          { key: 'questions' as const, label: '每题详情' },
          { key: 'methodology' as const, label: '实验设计' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            background: tab === t.key ? '#238636' : '#21262d', color: tab === t.key ? '#fff' : '#8b949e',
          }}>{t.label}</button>
        ))}
      </div>

      {tab === 'results' && <><HeroInsight /><OverviewCards /><ComparisonTable /><Insights /></>}
      {tab === 'details' && <><CategoryBreakdown /><DifficultyBreakdown /></>}
      {tab === 'questions' && <QuestionDetail />}
      {tab === 'methodology' && <Methodology />}
    </div>
  )
}
