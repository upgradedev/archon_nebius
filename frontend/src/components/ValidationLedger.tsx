import { List, Tag, Typography, Space } from 'antd'
import { CheckCircleOutlined, MinusCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import type { ValidationRule, ValidationState } from '../types/financial'

const { Text } = Typography

const STATE: Record<ValidationState, { color: string; label: string; icon: React.ReactNode }> = {
  pass: { color: 'success', label: 'PASS', icon: <CheckCircleOutlined /> },
  fail: { color: 'error', label: 'FAIL', icon: <CloseCircleOutlined /> },
  skip: { color: 'warning', label: 'DORMANT', icon: <MinusCircleOutlined /> },
}

interface Props {
  rules: ValidationRule[]
}

// The R1–R4 cross-document validation ledger. DORMANT (skip) rules never fire
// because the register fields they read are never extracted — the harness's
// keystone finding, surfaced here instead of silently passing a broken close.
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
        R2 &amp; R4 are dormant — the register fields they depend on are never extracted.
        The evaluation harness measures this, rather than assuming the checks fire.
      </Text>
    </Space>
  )
}
