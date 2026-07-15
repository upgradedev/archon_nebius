import { Row, Col, Statistic, Progress, Typography, Space, Tag } from 'antd'
import { ArrowRightOutlined, TeamOutlined } from '@ant-design/icons'
import type { PayrollGap } from '../types/financial'

const { Text } = Typography

const fmt = (v: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

interface Props {
  gap: PayrollGap
}

// Compare two values reported by different payroll documents: bank-confirmed net
// wages and register-reported employer cost. This is not proof that separate tax
// or social-insurance remittances were paid. Rendered without Recharts so it draws
// reliably in a headless capture.
export default function PayrollGapCard({ gap }: Props) {
  // Difference between the two reported values. Headline gapPct expresses it over
  // bank net; the bar expresses it as a share of registered employer cost.
  const gapAmount = gap.trueEmployerCost - gap.bankTransferNet
  const pct = Math.min(100, Math.round((gapAmount / gap.trueEmployerCost) * 100))

  return (
    <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <Row align="middle" gutter={[16, 16]} wrap={false}>
        <Col flex="1">
          <Statistic
            title="Bank transfer (net)"
            value={gap.bankTransferNet}
            formatter={v => fmt(Number(v))}
            valueStyle={{ color: '#94a3b8' }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>The net-wages component</Text>
        </Col>
        <Col flex="0 0 auto">
          <ArrowRightOutlined style={{ fontSize: 24, color: '#34d399' }} />
        </Col>
        <Col flex="1">
          <Statistic
            title="Registered employer cost"
            value={gap.trueEmployerCost}
            formatter={v => fmt(Number(v))}
            valueStyle={{ color: '#34d399' }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>Total reported by the payroll register</Text>
        </Col>
        <Col flex="0 0 auto" style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 40, fontWeight: 900, color: '#34d399', lineHeight: 1 }}>
            +{gap.gapPct.toFixed(0)}%
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>registered cost above bank net</Text>
        </Col>
      </Row>

      <div>
        <Row justify="space-between" style={{ marginBottom: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>Difference ({pct}% of registered cost)</Text>
          <Text strong style={{ color: '#34d399' }}>{fmt(gapAmount)}</Text>
        </Row>
        <Progress
          percent={pct}
          showInfo={false}
          strokeColor="#34d399"
          trailColor="#1f2937"
          status="active"
        />
      </div>

      <Space>
        <Tag icon={<TeamOutlined />} color="green">{gap.employeeCount} employees</Tag>
        <Tag color="blue">3-document comparison</Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Bank confirmation · payroll register · payslips → one linked payroll event
        </Text>
      </Space>
    </Space>
  )
}
