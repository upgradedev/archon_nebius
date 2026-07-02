import { useState } from 'react'
import { Row, Col, Card, Statistic, Tag, Modal, Typography } from 'antd'
import {
  ArrowUpOutlined, ArrowDownOutlined,
  EuroOutlined, FileTextOutlined, PercentageOutlined,
} from '@ant-design/icons'
import type { FinancialReport } from '../types/financial'
import PnLChart from './PnLChart'
import CashFlowChart from './CashFlowChart'
import ExpenseBreakdown from './ExpenseBreakdown'

const { Text } = Typography

interface Props {
  report: FinancialReport
}

const fmt = (v: number) =>
  new Intl.NumberFormat('en-EU', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

// Tiles that drill into a detail view. Purely-informational tiles (Revenue
// Growth, Invoices) are intentionally absent — they have no dedicated detail
// component to open, so they stay non-interactive. This gate mirrors the Azure
// build, which decides tile clickability from a TILE_DOC_TYPES map.
type TileKey = 'Revenue' | 'Net Profit' | 'Gross Margin' | 'Collection Rate'

export default function MetricsCards({ report }: Props) {
  const { keyMetrics: metrics, pnl } = report
  const growthPositive = metrics.revenueGrowthPct >= 0
  const [activeTile, setActiveTile] = useState<TileKey | null>(null)

  // Each drillable tile maps to the relevant detail view. Non-drillable tiles
  // are simply absent from this map (used as the clickability gate below).
  const TILE_DETAIL: Record<TileKey, { title: string; hint: string; node: React.ReactNode }> = {
    'Revenue': {
      title: 'Revenue vs Expenses vs Net Profit',
      hint: 'How this period’s revenue converts to net profit after expenses.',
      node: <PnLChart data={pnl} />,
    },
    'Net Profit': {
      title: 'Revenue vs Expenses vs Net Profit',
      hint: 'Net profit is what remains after every expense is subtracted from revenue.',
      node: <PnLChart data={pnl} />,
    },
    'Gross Margin': {
      title: 'Expense Breakdown',
      hint: 'The expense mix that drives the margin on this period’s revenue.',
      node: <ExpenseBreakdown data={report.expenseBreakdown} />,
    },
    'Collection Rate': {
      title: 'Cash Flow',
      hint: 'Operating, investing and financing cash movements behind collections.',
      node: <CashFlowChart data={report.cashFlow} />,
    },
  }

  const isDrillable = (label: string): label is TileKey => label in TILE_DETAIL

  // Shared interactive props for a drillable tile: hover affordance, pointer
  // cursor, click + keyboard (Enter/Space) activation and a button role so the
  // tile is reachable and operable without a mouse. Non-drillable tiles get an
  // empty object and stay inert.
  const tileProps = (label: string) => {
    if (!isDrillable(label)) return {}
    const open = () => setActiveTile(label)
    return {
      hoverable: true,
      onClick: open,
      role: 'button',
      tabIndex: 0,
      'aria-label': `${label} — open detail`,
      onKeyDown: (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          open()
        }
      },
      style: { cursor: 'pointer' as const },
    }
  }

  return (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Revenue')}>
            <Statistic
              title="Revenue"
              value={pnl.revenue}
              formatter={v => fmt(Number(v))}
              prefix={<EuroOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Net Profit')}>
            <Statistic
              title="Net Profit"
              value={pnl.netProfit}
              formatter={v => fmt(Number(v))}
              valueStyle={{ color: pnl.netProfit >= 0 ? '#22c55e' : '#f43f5e' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Gross Margin')}>
            <Statistic
              title="Gross Margin"
              value={pnl.grossMarginPct}
              precision={1}
              suffix="%"
              prefix={<PercentageOutlined />}
              valueStyle={{ color: '#6366f1' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Revenue Growth')}>
            <Statistic
              title="Revenue Growth"
              value={Math.abs(metrics.revenueGrowthPct)}
              precision={1}
              suffix="%"
              prefix={growthPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              valueStyle={{ color: growthPositive ? '#22c55e' : '#f43f5e' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Invoices')}>
            <Statistic
              title="Invoices"
              value={metrics.invoiceCount}
              prefix={<FileTextOutlined />}
            />
            <Tag style={{ marginTop: 4 }}>
              avg {fmt(metrics.avgInvoiceValue)}
            </Tag>
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Collection Rate')}>
            <Statistic
              title="Collection Rate"
              value={metrics.collectionRatePct}
              precision={1}
              suffix="%"
              valueStyle={{ color: metrics.collectionRatePct >= 90 ? '#22c55e' : '#f97316' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Tile drill-down — opens the relevant detail view. A Modal (not a
          sliding Drawer) keeps the Recharts ResponsiveContainer sized on mount
          so the chart draws reliably; Escape / mask click / the ✕ all close it. */}
      <Modal
        open={!!activeTile}
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <FileTextOutlined style={{ color: '#6366f1' }} />
            {activeTile ? TILE_DETAIL[activeTile].title : ''}
          </span>
        }
        onCancel={() => setActiveTile(null)}
        footer={null}
        width={Math.min(typeof window !== 'undefined' ? window.innerWidth - 48 : 720, 720)}
        destroyOnHidden
      >
        {activeTile && (
          <>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {TILE_DETAIL[activeTile].hint}
            </Text>
            <div style={{ marginTop: 12 }}>{TILE_DETAIL[activeTile].node}</div>
          </>
        )}
      </Modal>
    </>
  )
}
