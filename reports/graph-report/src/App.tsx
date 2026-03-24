import { useState } from 'react'
import { HeroSection } from './components/HeroSection.tsx'
import { DataOverview } from './components/DataOverview.tsx'
import { GraphConcepts } from './components/GraphConcepts.tsx'
import { TransformDemo } from './components/TransformDemo.tsx'
import { GraphVisualization } from './components/GraphVisualization.tsx'
import { TraversalDemo } from './components/TraversalDemo.tsx'
import { SolutionComparison } from './components/SolutionComparison.tsx'
import { BenchmarkResults } from './components/BenchmarkResults.tsx'

const TABS = [
  { key: 'hero', label: '首页' },
  { key: 'overview', label: '数据概览' },
  { key: 'concepts', label: '图数据库原理' },
  { key: 'transform', label: '转换过程' },
  { key: 'visualization', label: '图谱可视化' },
  { key: 'traversal', label: '图遍历演示' },
  { key: 'solutions', label: '方案对比' },
  { key: 'benchmark', label: 'Benchmark' },
] as const

type TabKey = (typeof TABS)[number]['key']

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('hero')

  const renderContent = () => {
    switch (activeTab) {
      case 'hero':
        return <HeroSection />
      case 'overview':
        return <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}><DataOverview /></div>
      case 'concepts':
        return <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}><GraphConcepts /></div>
      case 'transform':
        return <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}><TransformDemo /></div>
      case 'visualization':
        return <GraphVisualization />
      case 'traversal':
        return <TraversalDemo />
      case 'solutions':
        return <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}><SolutionComparison /></div>
      case 'benchmark':
        return <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto', overflowY: 'auto', height: '100%' }}><BenchmarkResults /></div>
    }
  }

  return (
    <>
      <nav className="tab-bar">
        <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--accent)', marginRight: 16, whiteSpace: 'nowrap' }}>
          Graph Report
        </span>
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <main style={{ flex: 1, overflow: 'hidden', height: 'calc(100vh - 48px)' }}>
        {renderContent()}
      </main>
    </>
  )
}

export default App
