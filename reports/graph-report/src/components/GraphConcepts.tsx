const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 24,
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
}

const iconCircle: React.CSSProperties = {
  width: 40,
  height: 40,
  borderRadius: '50%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 18,
  flexShrink: 0,
}

const titleStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
}

const bodyStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  lineHeight: 1.7,
}

const compactTable: React.CSSProperties = {
  fontSize: 12,
  borderCollapse: 'collapse',
  width: '100%',
}

function ConceptCard({ icon, color, title, children }: {
  icon: string
  color: string
  title: string
  children: React.ReactNode
}) {
  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ ...iconCircle, background: color + '22', color }}>{icon}</div>
        <h3 style={titleStyle}>{title}</h3>
      </div>
      <div style={bodyStyle}>{children}</div>
    </div>
  )
}

export function GraphConcepts() {
  return (
    <div className="section">
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>图数据库原理</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 32 }}>
        理解图数据库的核心概念、与 MySQL 的差异以及在 ChatBI 场景中的价值。
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
        gap: 16,
      }}>
        {/* Card 1: What is Graph DB */}
        <ConceptCard icon="&#9673;" color="#58a6ff" title="什么是图数据库">
          <p>
            图数据库是一种以<strong style={{ color: 'var(--text)' }}>节点（Node）</strong>和
            <strong style={{ color: 'var(--text)' }}>边（Edge）</strong>为核心存储单元的数据库。
            不同于关系型数据库用 JOIN 连接表，图数据库把「关系」作为一等公民直接存储，
            使得多跳关联查询的性能远超传统 SQL。
          </p>
          <p style={{ marginTop: 8 }}>
            典型应用场景：社交网络分析、知识图谱、推荐引擎、欺诈检测、Schema 关系可视化。
          </p>
        </ConceptCard>

        {/* Card 2: Property Graph */}
        <ConceptCard icon="&#9670;" color="#bc8cff" title="Property Graph 模型">
          <p>
            Property Graph 是最主流的图数据模型，核心元素：
          </p>
          <ul style={{ paddingLeft: 18, margin: '8px 0' }}>
            <li><strong style={{ color: 'var(--text)' }}>Node</strong> - 实体（如一张表、一个列）</li>
            <li><strong style={{ color: 'var(--text)' }}>Edge</strong> - 有向关系（如 REFERENCES、HAS_COLUMN）</li>
            <li><strong style={{ color: 'var(--text)' }}>Label</strong> - 类型标签（TableNode、ColumnNode）</li>
            <li><strong style={{ color: 'var(--text)' }}>Property</strong> - 键值属性（name, domain, type...）</li>
          </ul>
          <pre style={{ fontSize: 12 }}>
{`(:TableNode {name:"qft_joint_tenants", domain:"租客"})
  -[:REFERENCES {column:"room_id"}]->
(:TableNode {name:"qft_joint_room", domain:"房间"})`}
          </pre>
        </ConceptCard>

        {/* Card 3: Why Graph vs MySQL */}
        <ConceptCard icon="&#8644;" color="#3fb950" title="为什么用图谱而非直接查 MySQL">
          <p>在 ChatBI / Text-to-SQL 场景中，LLM 需要了解表结构才能生成正确的 SQL：</p>
          <table style={compactTable}>
            <thead>
              <tr>
                <th style={{ padding: '6px 8px' }}>对比维度</th>
                <th style={{ padding: '6px 8px' }}>直接用 MySQL Schema</th>
                <th style={{ padding: '6px 8px' }}>Graph 辅助</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>Schema 范围</td>
                <td style={{ padding: '6px 8px' }}>全量 77 表 = 海量 Token</td>
                <td style={{ padding: '6px 8px' }}>图遍历精准选 3-5 张表</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>JOIN 路径</td>
                <td style={{ padding: '6px 8px' }}>LLM 需猜测外键</td>
                <td style={{ padding: '6px 8px' }}>图谱直接给出连接路径</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>上下文质量</td>
                <td style={{ padding: '6px 8px' }}>噪声高，无关表干扰</td>
                <td style={{ padding: '6px 8px' }}>高信噪比精准上下文</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>性能</td>
                <td style={{ padding: '6px 8px' }}>全量解析慢</td>
                <td style={{ padding: '6px 8px' }}>图遍历 O(V+E) 毫秒级</td>
              </tr>
            </tbody>
          </table>
        </ConceptCard>

        {/* Card 4: Schema Graph vs Data Graph */}
        <ConceptCard icon="&#9881;" color="#f0883e" title="Schema Graph vs Data Graph">
          <p>图谱有两个层次，本项目聚焦 <strong style={{ color: 'var(--accent)' }}>Schema Graph</strong>：</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 8 }}>
            <div style={{
              background: 'var(--bg)',
              borderRadius: 6,
              padding: 12,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontWeight: 600, color: 'var(--accent)', marginBottom: 4, fontSize: 13 }}>
                Schema Graph (元数据图)
              </div>
              <ul style={{ paddingLeft: 16, margin: 0, fontSize: 12 }}>
                <li>节点 = 表/列定义</li>
                <li>边 = 外键/引用关系</li>
                <li>用途 = 辅助 LLM 理解结构</li>
                <li>规模 = 77 节点 + 135 边</li>
              </ul>
            </div>
            <div style={{
              background: 'var(--bg)',
              borderRadius: 6,
              padding: 12,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontWeight: 600, color: 'var(--purple)', marginBottom: 4, fontSize: 13 }}>
                Data Graph (数据图)
              </div>
              <ul style={{ paddingLeft: 16, margin: 0, fontSize: 12 }}>
                <li>节点 = 具体记录行</li>
                <li>边 = 实际引用值</li>
                <li>用途 = 复杂关联查询</li>
                <li>规模 = 百万级节点</li>
              </ul>
            </div>
          </div>
        </ConceptCard>

        {/* Card 5: Cypher */}
        <ConceptCard icon="&#62;" color="#d29922" title="Cypher 查询语言">
          <p>
            Cypher 是图数据库的声明式查询语言（类似 SQL 之于关系数据库），用 ASCII Art 风格表达图模式：
          </p>
          <pre style={{ fontSize: 12, marginTop: 8 }}>
{`// 查找租客表的所有关联表（1跳）
MATCH (t:TableNode {name:"qft_joint_tenants"})
      -[:REFERENCES]-(neighbor)
RETURN neighbor.name, neighbor.domain

// 查找两个表之间的最短路径
MATCH path = shortestPath(
  (a:TableNode {name:"qft_joint_tenants"})
  -[:REFERENCES*..5]-
  (b:TableNode {name:"qft_joint_housing"})
)
RETURN [n IN nodes(path) | n.name]`}
          </pre>
        </ConceptCard>

        {/* Card 6: DB Comparison */}
        <ConceptCard icon="&#9878;" color="#f85149" title="图数据库选型对比">
          <table style={compactTable}>
            <thead>
              <tr>
                <th style={{ padding: '6px 8px' }}>特性</th>
                <th style={{ padding: '6px 8px' }}>FalkorDB</th>
                <th style={{ padding: '6px 8px' }}>Neo4j</th>
                <th style={{ padding: '6px 8px' }}>Kuzu</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>类型</td>
                <td style={{ padding: '6px 8px' }}>内存图 (Redis模块)</td>
                <td style={{ padding: '6px 8px' }}>原生图数据库</td>
                <td style={{ padding: '6px 8px' }}>嵌入式图DB</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>查询语言</td>
                <td style={{ padding: '6px 8px' }}>Cypher 子集</td>
                <td style={{ padding: '6px 8px' }}>Cypher 完整</td>
                <td style={{ padding: '6px 8px' }}>Cypher 兼容</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>部署难度</td>
                <td style={{ padding: '6px 8px', color: 'var(--green)' }}>低 (Docker)</td>
                <td style={{ padding: '6px 8px', color: 'var(--yellow)' }}>中 (JVM)</td>
                <td style={{ padding: '6px 8px', color: 'var(--green)' }}>极低 (嵌入式)</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>适合场景</td>
                <td style={{ padding: '6px 8px' }}>实时低延迟</td>
                <td style={{ padding: '6px 8px' }}>企业级大规模</td>
                <td style={{ padding: '6px 8px' }}>OLAP / 分析</td>
              </tr>
              <tr>
                <td style={{ padding: '6px 8px', color: 'var(--text)' }}>开源</td>
                <td style={{ padding: '6px 8px', color: 'var(--green)' }}>是 (Apache 2.0)</td>
                <td style={{ padding: '6px 8px', color: 'var(--yellow)' }}>社区版 GPLv3</td>
                <td style={{ padding: '6px 8px', color: 'var(--green)' }}>是 (MIT)</td>
              </tr>
            </tbody>
          </table>
          <p style={{ marginTop: 8, fontSize: 12 }}>
            本项目推荐 <strong style={{ color: 'var(--accent)' }}>FalkorDB</strong>：
            Schema Graph 规模小（百级节点），内存图查询延迟极低（&lt;1ms），
            且与 Redis 生态无缝集成。
          </p>
        </ConceptCard>

        {/* Card 7: Query Pipeline */}
        <ConceptCard icon="&#9654;" color="#58a6ff" title="完整查询流程（5 步）">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { step: 1, title: '意图解析', desc: 'LLM 从自然语言提取关键词和业务实体（如"租客""欠款"）' },
              { step: 2, title: '图谱定位', desc: '关键词匹配图谱中的 TableNode / ColumnNode，定位起始节点' },
              { step: 3, title: '图遍历扩展', desc: '从起始节点沿 REFERENCES 边做 1-2 跳 BFS，收集关联表' },
              { step: 4, title: 'Schema 精简', desc: '仅取遍历命中的表的 DDL 片段，组成精简 Schema 上下文' },
              { step: 5, title: 'SQL 生成', desc: 'LLM 基于精简 Schema + 原始问题生成精准 SQL 并执行' },
            ].map(item => (
              <div key={item.step} style={{
                display: 'flex',
                gap: 12,
                alignItems: 'flex-start',
                padding: '8px 12px',
                background: 'var(--bg)',
                borderRadius: 6,
                border: '1px solid var(--border)',
              }}>
                <div style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: 'var(--accent)',
                  color: '#0d1117',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                }}>
                  {item.step}
                </div>
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{item.title}</div>
                  <div style={{ fontSize: 12 }}>{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </ConceptCard>

        {/* Card 8: Inference Rules */}
        <ConceptCard icon="&#9889;" color="#3fb950" title="关系推断规则">
          <p>
            MySQL 中大量外键关系并未显式声明（无 FOREIGN KEY 约束），
            我们通过命名模式自动推断：
          </p>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontWeight: 600, color: 'var(--green)', fontSize: 13, marginBottom: 4 }}>
              高置信度规则（已采纳）
            </div>
            <ul style={{ paddingLeft: 18, margin: '4px 0', fontSize: 12 }}>
              <li><code>*_id</code> 列 &rarr; 匹配 <code>qft_*</code> 表名去掉前缀 &rarr; 建立 REFERENCES 边</li>
              <li><code>housing_id</code> &rarr; <code>qft_joint_housing</code></li>
              <li><code>room_id</code> &rarr; <code>qft_joint_room</code></li>
              <li><code>tenants_id</code> &rarr; <code>qft_joint_tenants</code></li>
              <li><code>store_id</code> &rarr; <code>qft_store</code></li>
            </ul>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)', fontSize: 13, marginBottom: 4 }}>
              跳过的列（低置信度）
            </div>
            <ul style={{ paddingLeft: 18, margin: '4px 0', fontSize: 12 }}>
              <li><code>id</code> &mdash; 自增主键，非外键</li>
              <li><code>create_id</code> / <code>update_id</code> &mdash; 操作人，非业务关系</li>
              <li><code>parent_id</code> &mdash; 自引用，图谱中暂不处理</li>
              <li><code>del_id</code> / <code>status</code> 等 &mdash; 状态字段</li>
            </ul>
          </div>
        </ConceptCard>
      </div>
    </div>
  )
}
