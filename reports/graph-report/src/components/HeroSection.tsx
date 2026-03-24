import { useState, useEffect } from 'react'

interface StatItem {
  label: string
  value: number
  suffix: string
}

const STATS: StatItem[] = [
  { label: '数据表', value: 77, suffix: '张' },
  { label: '字段总数', value: 2972, suffix: '列' },
  { label: '表间关系', value: 135, suffix: '条' },
  { label: '业务域', value: 8, suffix: '个' },
]

function AnimatedNumber({ target, duration = 1500 }: { target: number; duration?: number }) {
  const [current, setCurrent] = useState(0)

  useEffect(() => {
    const startTime = Date.now()
    const tick = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setCurrent(Math.round(target * eased))
      if (progress < 1) {
        requestAnimationFrame(tick)
      }
    }
    requestAnimationFrame(tick)
  }, [target, duration])

  return <>{current.toLocaleString()}</>
}

export function HeroSection() {
  return (
    <div style={{
      minHeight: 'calc(100vh - 45px)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(180deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
      position: 'relative',
      overflow: 'hidden',
      padding: '60px 24px',
    }}>
      {/* Background decoration */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 600,
        height: 600,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(88,166,255,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Icon */}
      <div style={{
        fontSize: 48,
        marginBottom: 24,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        color: 'var(--text-secondary)',
      }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#8b949e" strokeWidth="1.5">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" strokeWidth="2">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" strokeWidth="1.5">
          <circle cx="12" cy="5" r="3" />
          <circle cx="5" cy="19" r="3" />
          <circle cx="19" cy="19" r="3" />
          <line x1="12" y1="8" x2="5" y2="16" />
          <line x1="12" y1="8" x2="19" y2="16" />
          <line x1="5" y1="19" x2="19" y2="19" />
        </svg>
      </div>

      {/* Title */}
      <h1 style={{
        fontSize: 48,
        fontWeight: 800,
        background: 'linear-gradient(135deg, #e6edf3 0%, #58a6ff 50%, #bc8cff 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
        textAlign: 'center',
        lineHeight: 1.2,
        marginBottom: 8,
      }}>
        MySQL &rarr; Graph Database
      </h1>

      <h2 style={{
        fontSize: 20,
        fontWeight: 400,
        color: 'var(--text-secondary)',
        textAlign: 'center',
        marginBottom: 48,
        maxWidth: 600,
        lineHeight: 1.6,
      }}>
        全房通 MySQL Schema 图谱化转换分析报告
      </h2>

      <p style={{
        fontSize: 14,
        color: 'var(--text-secondary)',
        textAlign: 'center',
        maxWidth: 640,
        lineHeight: 1.8,
        marginBottom: 48,
      }}>
        通过分析 MySQL 数据库中 77 张表的外键关系和命名模式，自动推断表间引用关系，
        构建 Property Graph 模型。本报告展示了完整的转换过程、图谱可视化及基于图遍历的
        ChatBI Schema 精简策略。
      </p>

      {/* Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 24,
        maxWidth: 700,
        width: '100%',
      }}>
        {STATS.map((stat, i) => (
          <div key={stat.label} className="fade-in" style={{
            textAlign: 'center',
            padding: '24px 16px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 12,
            animationDelay: `${i * 100}ms`,
          }}>
            <div style={{
              fontSize: 36,
              fontWeight: 800,
              color: 'var(--accent)',
              lineHeight: 1.2,
            }}>
              <AnimatedNumber target={stat.value} />
            </div>
            <div style={{
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginTop: 4,
            }}>
              {stat.label} ({stat.suffix})
            </div>
          </div>
        ))}
      </div>

      {/* Bottom hint */}
      <div style={{
        marginTop: 64,
        color: 'var(--text-secondary)',
        fontSize: 13,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        opacity: 0.6,
      }}>
        <span>&#8593;</span> 使用顶部 Tab 切换查看各部分内容
      </div>
    </div>
  )
}
