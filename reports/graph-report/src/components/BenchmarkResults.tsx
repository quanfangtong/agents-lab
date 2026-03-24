/**
 * Benchmark 结果 Tab：展示 A/B test 对比数据
 * 数据从 benchmarkData.json 加载（benchmark 跑完后拷入）
 */
import { useState } from 'react'

interface BenchmarkEntry {
  question_id: string
  question: string
  solution: string
  model: string
  category: string
  difficulty: string
  domain: string
  success: boolean
  generated_sql: string
  error: string | null
  total_ms: number
  schema_token_estimate: number
  schema_tables: string[]
  table_recall: number | null
  execution_result: Record<string, unknown>[]
  row_count: number
}

interface BenchmarkData {
  timestamp: string
  config: { solutions: string[]; models: string[]; question_count: number }
  summary: Record<string, Record<string, { total: number; success: number; success_rate: string; avg_ms: number; avg_tokens: number }>>
  results: BenchmarkEntry[]
}

import rawBenchmark from '../data/benchmarkData.json'
const benchmarkData = rawBenchmark as unknown as BenchmarkData

const SOLUTION_COLORS: Record<string, string> = {
  'A_Baseline': '#8b949e',
  'B_Kuzu': '#10b981',
  'C_Neo4j': '#3b82f6',
  'D_FalkorDB': '#f59e0b',
}

const SOLUTION_LABELS: Record<string, string> = {
  'A_Baseline': 'A. Baseline',
  'B_Kuzu': 'B. Kuzu',
  'C_Neo4j': 'C. Neo4j',
  'D_FalkorDB': 'D. FalkorDB',
}

export function BenchmarkResults() {
  const [expandedQ, setExpandedQ] = useState<string | null>(null)

  if (!benchmarkData || !benchmarkData.results || benchmarkData.results.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <h3 style={{ marginBottom: 12 }}>Benchmark 尚未运行</h3>
        <p style={{ color: '#8b949e', fontSize: 14, lineHeight: 1.8 }}>
          运行 benchmark 后将结果文件拷贝到此处：<br />
          <code>cp benchmarks/results/benchmark_*.json reports/graph-report/src/data/benchmarkData.json</code><br />
          然后重新 build：<code>npm run build</code>
        </p>
      </div>
    )
  }

  const data = benchmarkData
  const solutions = Object.keys(data.summary)
  // 按题目分组
  const questionIds = [...new Set(data.results.map(r => r.question_id))].sort()

  return (
    <div>
      <p style={{ color: '#8b949e', marginBottom: 8, fontSize: 13 }}>
        {data.config.question_count} 题 × {data.config.solutions.length} 方案 × {data.config.models.length} 模型 | {data.timestamp}
      </p>

      {/* 总览：成功率柱状图 */}
      <h3 style={{ fontSize: 18, marginTop: 24, marginBottom: 16 }}>成功率对比</h3>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 32 }}>
        {solutions.map(sol => {
          const modelData = data.summary[sol]
          return Object.entries(modelData).map(([model, stats]) => {
            const pct = stats.total ? (stats.success / stats.total * 100) : 0
            return (
              <div key={`${sol}-${model}`} style={{
                background: '#161b22', border: '1px solid #21262d', borderRadius: 8,
                padding: 16, minWidth: 180, flex: '1 1 180px',
              }}>
                <div style={{ fontSize: 12, color: SOLUTION_COLORS[sol] || '#8b949e', fontWeight: 600, marginBottom: 4 }}>
                  {SOLUTION_LABELS[sol] || sol}
                </div>
                <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 8 }}>{model}</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: pct >= 70 ? '#7ee787' : pct >= 40 ? '#f59e0b' : '#ff7b72' }}>
                  {pct.toFixed(0)}%
                </div>
                <div style={{ fontSize: 12, color: '#8b949e' }}>{stats.success_rate}</div>
                {/* 进度条 */}
                <div style={{ height: 6, background: '#21262d', borderRadius: 3, marginTop: 8, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${pct}%`, background: SOLUTION_COLORS[sol] || '#58a6ff', borderRadius: 3, transition: 'width 0.5s' }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 11, color: '#8b949e' }}>
                  <span>avg {stats.avg_ms}ms</span>
                  <span>~{stats.avg_tokens} tokens</span>
                </div>
              </div>
            )
          })
        })}
      </div>

      {/* 关键指标对比表 */}
      <h3 style={{ fontSize: 18, marginBottom: 16 }}>关键指标对比</h3>
      <div style={{ overflowX: 'auto', marginBottom: 32 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #30363d' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', color: '#8b949e' }}>方案</th>
              <th style={{ padding: '8px 12px', textAlign: 'left', color: '#8b949e' }}>模型</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', color: '#8b949e' }}>成功率</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', color: '#8b949e' }}>平均耗时</th>
              <th style={{ padding: '8px 12px', textAlign: 'right', color: '#8b949e' }}>平均 Tokens</th>
            </tr>
          </thead>
          <tbody>
            {solutions.flatMap(sol =>
              Object.entries(data.summary[sol]).map(([model, stats]) => (
                <tr key={`${sol}-${model}`} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={{ padding: '8px 12px', color: SOLUTION_COLORS[sol], fontWeight: 600 }}>
                    {SOLUTION_LABELS[sol] || sol}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#8b949e' }}>{model}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'right', color: '#e6edf3', fontWeight: 600 }}>{stats.success_rate}</td>
                  <td style={{ padding: '8px 12px', textAlign: 'right', color: '#8b949e' }}>{stats.avg_ms}ms</td>
                  <td style={{ padding: '8px 12px', textAlign: 'right', color: '#8b949e' }}>~{stats.avg_tokens}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 每题明细 */}
      <h3 style={{ fontSize: 18, marginBottom: 16 }}>每题明细</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {questionIds.map(qid => {
          const qResults = data.results.filter(r => r.question_id === qid)
          const question = qResults[0]?.question || qid
          const isExpanded = expandedQ === qid
          const allSuccess = qResults.every(r => r.success)
          const anySuccess = qResults.some(r => r.success)

          return (
            <div key={qid} style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 6, overflow: 'hidden' }}>
              <div
                onClick={() => setExpandedQ(isExpanded ? null : qid)}
                style={{
                  padding: '10px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                  background: isExpanded ? '#1c2333' : 'transparent',
                }}
              >
                <span style={{ color: '#8b949e', fontSize: 12, minWidth: 36 }}>{qid}</span>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: allSuccess ? '#7ee787' : anySuccess ? '#f59e0b' : '#ff7b72',
                  flexShrink: 0,
                }} />
                <span style={{ fontSize: 13, flex: 1 }}>{question}</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  {qResults.map(r => (
                    <span key={`${r.solution}-${r.model}`} style={{
                      width: 16, height: 16, borderRadius: 3, fontSize: 9, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: r.success ? '#7ee78722' : '#ff7b7222',
                      color: r.success ? '#7ee787' : '#ff7b72',
                    }}>
                      {r.solution[0]}
                    </span>
                  ))}
                </div>
                <span style={{ color: '#8b949e', fontSize: 12 }}>{isExpanded ? '▲' : '▼'}</span>
              </div>

              {isExpanded && (
                <div style={{ padding: '0 14px 14px', borderTop: '1px solid #21262d' }}>
                  {qResults.map(r => (
                    <div key={`${r.solution}-${r.model}`} style={{
                      marginTop: 10, padding: 10, background: '#0d1117', borderRadius: 6,
                      border: `1px solid ${r.success ? '#21262d' : '#ff7b7233'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ color: SOLUTION_COLORS[r.solution], fontWeight: 600, fontSize: 12 }}>
                          {SOLUTION_LABELS[r.solution] || r.solution}
                        </span>
                        <span style={{ color: '#8b949e', fontSize: 11 }}>{r.model}</span>
                        <span style={{
                          padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                          background: r.success ? '#7ee78722' : '#ff7b7222',
                          color: r.success ? '#7ee787' : '#ff7b72',
                        }}>
                          {r.success ? 'OK' : 'FAIL'}
                        </span>
                        <span style={{ color: '#8b949e', fontSize: 11, marginLeft: 'auto' }}>
                          {r.total_ms}ms | ~{r.schema_token_estimate} tokens
                        </span>
                      </div>
                      <pre style={{
                        fontSize: 11, padding: 8, background: '#161b22', borderRadius: 4,
                        whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.5,
                        color: r.success ? '#79c0ff' : '#ff7b72',
                        maxHeight: 200, overflow: 'auto',
                      }}>
                        {r.generated_sql || 'N/A'}
                      </pre>
                      {r.error && (
                        <div style={{ fontSize: 11, color: '#ff7b72', marginTop: 4, padding: '4px 8px', background: '#ff7b7211', borderRadius: 4 }}>
                          {r.error}
                        </div>
                      )}
                      {r.success && r.execution_result && r.execution_result.length > 0 && (
                        <div style={{ fontSize: 11, color: '#7ee787', marginTop: 4 }}>
                          结果: {JSON.stringify(r.execution_result[0])}
                          {r.row_count > 1 && <span style={{ color: '#8b949e' }}> ... ({r.row_count} 行)</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
