import { List, Tag, Typography, Space } from 'antd'
import { CheckCircleOutlined, MinusCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import type { ValidationRule, ValidationState } from '../types/financial'

const { Text } = Typography

const STATE: Record<ValidationState, { color: string; label: string; icon: React.ReactNode }> = {
  pass: { color: 'success', label: 'PASS', icon: <CheckCircleOutlined /> },
  fail: { color: 'error', label: 'FAIL', icon: <CloseCircleOutlined /> },
  skip: { color: 'warning', label: 'SKIPPED', icon: <MinusCircleOutlined /> },
}

interface Props {
  rules: ValidationRule[]
}

// The R1–R4 cross-document validation ledger. A rule shows SKIPPED whenever its
// required documents or fields are absent. The offline perfect-input harness
// exercises all four rules on the synthetic cases where each rule applies.
export default function ValidationLedger({ rules }: Props) {
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <List
        size="small"
        dataSource={rules}
        renderItem={r => {
          const s = STATE[r.state]
          return (
            <List.Item
              key={r.id}
              actions={[
                <Tag key="state" color={s.color} icon={s.icon}>{s.label}</Tag>,
              ]}
            >
              <List.Item.Meta
                title={<Text strong>{r.id}</Text>}
                description={<Text type="secondary">{r.check}</Text>}
              />
            </List.Item>
          )
        }}
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        The offline 40-case perfect-input harness exercises R1–R4 on every applicable
        synthetic case. In an uploaded period, a rule is skipped when its required documents
        or extracted fields are absent.
      </Text>
    </Space>
  )
}
