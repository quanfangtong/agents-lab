/**
 * 方案对比 Tab：展示 5 种方案的架构差异和图数据库特性对比
 */
export function SolutionComparison() {
  const solutions = [
    {
      key: 'A', name: 'Baseline', subtitle: '全量 DDL 直投',
      color: '#8b949e',
      graph: '无',
      how: '获取 77 张表全部 DDL（~58K tokens）→ 整体作为 system prompt → LLM 生成 SQL',
      pros: ['实现最简单', '不遗漏任何表', '无需额外组件'],
      cons: ['Token 消耗巨大（~58K/次）', 'LLM 注意力被无关表分散', '成本高'],
      deploy: '无需部署',
      latency: '无图遍历开销',
    },
    {
      key: 'B', name: 'Kuzu', subtitle: '嵌入式 Schema Graph',
      color: '#10b981',
      graph: 'Kuzu（嵌入式，pip install）',
      how: '问题 → 关键词搜索图谱 → 1-2跳扩展 → 精简 DDL（~3-15K tokens）→ LLM 生成 SQL',
      pros: ['零运维，pip install', '列存储，分析快', 'Python 原生集成'],
      cons: ['单进程锁（不能并发）', '社区较小', '无 MCP Server'],
      deploy: 'pip install kuzu',
      latency: '图遍历 ~50-100ms',
    },
    {
      key: 'C', name: 'Neo4j', subtitle: '独立服务 Schema Graph',
      color: '#3b82f6',
      graph: 'Neo4j Community（Docker）',
      how: '同 Kuzu 的图遍历策略，但使用 Neo4j Cypher 查询',
      pros: ['生态最成熟', '全文索引', 'Browser 可视化', 'GDS 算法库'],
      cons: ['需要 Docker 部署', '社区版单机', '企业版昂贵'],
      deploy: 'docker run neo4j',
      latency: '图遍历 ~100-400ms',
    },
    {
      key: 'D', name: 'FalkorDB', subtitle: 'Redis 协议 Schema Graph',
      color: '#f59e0b',
      graph: 'FalkorDB（Docker，Redis 协议）',
      how: '同上，但使用 FalkorDB 的 Cypher 接口',
      pros: ['内存计算极快', 'Redis 协议低延迟', 'QueryWeaver 配套', '内置 MCP Server'],
      cons: ['需要 Docker', '社区相对小', '功能比 Neo4j 少'],
      deploy: 'docker run falkordb',
      latency: '图遍历 ~10-50ms',
    },
    {
      key: 'E', name: '静态规则', subtitle: '手工关键词映射',
      color: '#d2a8ff',
      graph: '无（Python dict）',
      how: '问题 → 硬编码的关键词→表映射 → 精简 DDL → LLM 生成 SQL',
      pros: ['无需任何外部依赖', '可控性最强', 'Token 消耗最低'],
      cons: ['需要手工维护映射', '无法发现新关系', '不可扩展'],
      deploy: '无需部署',
      latency: '< 1ms',
    },
  ]

  const graphDBs = [
    { name: 'Kuzu', type: '嵌入式', protocol: 'Python API', query: 'Cypher 兼容', storage: '列存储（磁盘）', deploy: 'pip install', mcp: '无', stars: '~1.5k', best: '本地 PoC / 单机分析' },
    { name: 'Neo4j', type: '独立服务', protocol: 'Bolt', query: 'Cypher', storage: '原生图存储', deploy: 'Docker / 安装包', mcp: '官方有', stars: '~14k', best: '生产环境 / 生态需求' },
    { name: 'FalkorDB', type: '独立服务', protocol: 'Redis', query: 'Cypher 子集', storage: '内存图', deploy: 'Docker', mcp: '官方有', stars: '~3.7k', best: '低延迟 / QueryWeaver' },
  ]

  return (
    <div>
      <p style={{ color: '#8b949e', marginBottom: 24, fontSize: 14 }}>
        对比 5 种 Text-to-SQL 方案的架构差异、图数据库特性和适用场景
      </p>

      {/* 方案架构对比 */}
      <h3 style={{ fontSize: 18, marginBottom: 16 }}>方案架构对比</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, marginBottom: 40 }}>
        {solutions.map(s => (
          <div key={s.key} style={{
            background: '#161b22', border: `1px solid ${s.color}33`, borderRadius: 8, padding: 16,
            borderTop: `3px solid ${s.color}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ background: s.color, color: '#0d1117', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700 }}>{s.key}</span>
              <span style={{ fontSize: 16, fontWeight: 600 }}>{s.name}</span>
            </div>
            <div style={{ fontSize: 12, color: s.color, marginBottom: 10 }}>{s.subtitle}</div>
            <div style={{ fontSize: 12, color: '#8b949e', marginBottom: 10, lineHeight: 1.6 }}>{s.how}</div>
            <div style={{ fontSize: 11, marginBottom: 6 }}>
              <span style={{ color: '#7ee787' }}>图数据库：</span>{s.graph}
            </div>
            <div style={{ fontSize: 11, marginBottom: 6 }}>
              <span style={{ color: '#79c0ff' }}>部署：</span>{s.deploy}
            </div>
            <div style={{ fontSize: 11, marginBottom: 10 }}>
              <span style={{ color: '#d2a8ff' }}>图遍历延迟：</span>{s.latency}
            </div>
            <div style={{ fontSize: 11 }}>
              <div style={{ color: '#7ee787', marginBottom: 4 }}>优势：</div>
              {s.pros.map((p, i) => <div key={i} style={{ color: '#8b949e', paddingLeft: 8 }}>+ {p}</div>)}
              <div style={{ color: '#ff7b72', marginTop: 6, marginBottom: 4 }}>劣势：</div>
              {s.cons.map((c, i) => <div key={i} style={{ color: '#8b949e', paddingLeft: 8 }}>- {c}</div>)}
            </div>
          </div>
        ))}
      </div>

      {/* 图数据库对比 */}
      <h3 style={{ fontSize: 18, marginBottom: 16 }}>图数据库特性对比</h3>
      <div style={{ overflowX: 'auto', marginBottom: 40 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #30363d' }}>
              {['', '类型', '协议', '查询语言', '存储方式', '部署', 'MCP Server', 'Stars', '最适合'].map(h => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#8b949e', fontSize: 12 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {graphDBs.map(db => (
              <tr key={db.name} style={{ borderBottom: '1px solid #21262d' }}>
                <td style={{ padding: '8px 12px', fontWeight: 600, color: '#58a6ff' }}>{db.name}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.type}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.protocol}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.query}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.storage}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.deploy}</td>
                <td style={{ padding: '8px 12px', color: db.mcp === '无' ? '#8b949e' : '#7ee787' }}>{db.mcp}</td>
                <td style={{ padding: '8px 12px', color: '#8b949e' }}>{db.stars}</td>
                <td style={{ padding: '8px 12px', color: '#f59e0b', fontSize: 12 }}>{db.best}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 流程对比图 */}
      <h3 style={{ fontSize: 18, marginBottom: 16 }}>查询流程对比</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 16 }}>
          <h4 style={{ fontSize: 14, marginBottom: 12, color: '#8b949e' }}>Baseline（无图）</h4>
          <pre style={{ fontSize: 12, lineHeight: 1.8, color: '#79c0ff', whiteSpace: 'pre-wrap' }}>
{`用户提问
  ↓
获取 77 张表全量 DDL (~58K tokens)
  ↓
全部塞进 System Prompt
  ↓
LLM 生成 SQL（注意力被分散）
  ↓
MySQL 执行`}
          </pre>
        </div>
        <div style={{ background: '#161b22', border: '1px solid #58a6ff33', borderRadius: 8, padding: 16 }}>
          <h4 style={{ fontSize: 14, marginBottom: 12, color: '#58a6ff' }}>Graph-Enhanced（有图）</h4>
          <pre style={{ fontSize: 12, lineHeight: 1.8, color: '#7ee787', whiteSpace: 'pre-wrap' }}>
{`用户提问
  ↓
提取关键词
  ↓
图谱搜索 + 1-2跳遍历 (~100ms)
  ↓
精简到 5-10 张表 DDL (~3K tokens)
  ↓
LLM 生成 SQL（精准聚焦）
  ↓
MySQL 执行`}
          </pre>
        </div>
      </div>
    </div>
  )
}
