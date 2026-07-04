import { Row, Col, Statistic, Progress, Typography, Space, Tag } from 'antd'
import { ArrowRightOutlined, TeamOutlined } from '@ant-design/icons'
import type { PayrollGap } from '../types/financial'

const { Text } = Typography

const fmt = (v: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

interface Props {
  gap: PayrollGap
}

// The core "hidden cost" insight: the bank transfer (net) understates the true
// employer cost. Rendered without Recharts so it draws reliably in a headless
// capture — the wedge is a plain Progress bar, the figures are Statistics.
export default function PayrollGapCard({ gap }: Props) {
  const wedge = gap.trueEmployerCost - gap.bankTransferNet
  const pct = Math.min(100, Math.round((wedge / gap.trueEmployerCost) * 100))

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
          <Text type="secondary" style={{ fontSize: 12 }}>What actually left the account</Text>
        </Col>
        <Col flex="0 0 auto">
          <ArrowRightOutlined style={{ fontSize: 24, color: '#34d399' }} />
        </Col>
        <Col flex="1">
          <Statistic
            title="True employer cost"
            value={gap.trueEmployerCost}
            formatter={v => fmt(Number(v))}
            valueStyle={{ color: '#34d399' }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>Gross pay + employer social security</Text>
        </Col>
        <Col flex="0 0 auto" style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 40, fontWeight: 900, color: '#34d399', lineHeight: 1 }}>
            +{gap.gapPct.toFixed(0)}%
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>understated by the bank figure</Text>
        </Col>
      </Row>

      <div>
        <Row justify="space-between" style={{ marginBottom: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>Employer social-security wedge</Text>
          <Text strong style={{ color: '#34d399' }}>{fmt(wedge)}</Text>
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
        <Tag color="blue">3-document fusion</Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Bank confirmation · payroll register · payslips → one financial event
        </Text>
      </Space>
    </Space>
  )
}
