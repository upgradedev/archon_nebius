import { Row, Col, Card, Statistic, Tag } from 'antd'
import {
  ArrowUpOutlined, ArrowDownOutlined,
  EuroOutlined, FileTextOutlined, PercentageOutlined,
} from '@ant-design/icons'
import type { KeyMetrics, MonthlyPnL } from '../types/financial'

interface Props {
  metrics: KeyMetrics
  pnl: MonthlyPnL
}

const fmt = (v: number) =>
  new Intl.NumberFormat('en-EU', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

export default function MetricsCards({ metrics, pnl }: Props) {
  const growthPositive = metrics.revenueGrowthPct >= 0

  return (
    <Row gutter={[16, 16]}>
      <Col xs={12} sm={8} md={4}>
        <Card size="small">
          <Statistic
            title="Revenue"
            value={pnl.revenue}
            formatter={v => fmt(Number(v))}
            prefix={<EuroOutlined />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} md={4}>
        <Card size="small">
          <Statistic
            title="Net Profit"
            value={pnl.netProfit}
            formatter={v => fmt(Number(v))}
            valueStyle={{ color: pnl.netProfit >= 0 ? '#22c55e' : '#f43f5e' }}
          />
        </Card>
      </Col>
      <Col xs={12} sm={8} md={4}>
        <Card size="small">
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
        <Card size="small">
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
        <Card size="small">
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
        <Card size="small">
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
  )
}
