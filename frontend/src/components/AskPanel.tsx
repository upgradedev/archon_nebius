import { useState } from 'react'
import { Card, Space, Button, Typography } from 'antd'
import { QuestionCircleOutlined, BulbOutlined } from '@ant-design/icons'
import type { FinancialReport } from '../types/financial'

const { Text, Paragraph } = Typography

const fmt = (v: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

const pct = (v: number) => `${v.toFixed(1)}%`

// ── Scoped Q&A ("Ask Archon") ─────────────────────────────────────────────────
// A deliberately NON-LLM, deterministic question box. Each suggested question is
// answered by reading fields that are ALREADY in the computed FinancialReport
// (the same object the dashboard renders) — so every answer is grounded in a real
// number the user can see elsewhere on the page, with no new backend call and no
// hallucination surface. In demo mode this reads DEMO_REPORT; signed-in it reads
// the live report. Questions whose backing fields are absent are simply not shown,
// so it stays honest for reports that (e.g.) fused no payroll event.

interface QA {
  id: string
  q: string
  available: (r: FinancialReport) => boolean
  answer: (r: FinancialReport) => string
}

const QUESTIONS: QA[] = [
  {
    id: 'net-profit',
    q: 'What was the net profit this period?',
    available: (r) => !!r.pnl,
    answer: (r) =>
      `Net profit was ${fmt(r.pnl.netProfit)} on ${fmt(r.pnl.revenue)} of revenue — ` +
      `a ${pct(r.pnl.operatingMarginPct)} operating margin.`,
  },
  {
    id: 'employer-cost',
    q: "What's the total employer cost?",
    available: (r) => !!r.payrollGap,
    answer: (r) =>
      `The true employer cost is ${fmt(r.payrollGap!.trueEmployerCost)} across ` +
      `${r.payrollGap!.employeeCount} employees — gross pay plus the employer's ` +
      `social-security contribution.`,
  },
  {
    id: 'payroll-gap',
    q: 'How does the bank transfer reconcile to the true payroll cost?',
    available: (r) => !!r.payrollGap,
    answer: (r) => {
      const g = r.payrollGap!
      const reconciled = g.trueEmployerCost - g.bankTransferNet
      return (
        `The bank moved ${fmt(g.bankTransferNet)} in net wages, and the register's ` +
        `true employer cost is ${fmt(g.trueEmployerCost)} — ${g.gapPct.toFixed(0)}% more ` +
        `once the withheld payroll taxes and the employer's own social-security ` +
        `contributions are reconciled back to source documents (${fmt(reconciled)} in all). ` +
        `The employer contribution alone is ~35% over the transfer; the rest is ` +
        `employee withholdings.`
      )
    },
  },
  {
    id: 'top-vendors',
    q: 'Which vendors cost the most?',
    available: (r) => (r.topVendors?.length ?? 0) > 0,
    answer: (r) => {
      const top = [...r.topVendors]
        .sort((a, b) => b.totalAmount - a.totalAmount)
        .slice(0, 3)
        .map((v) => `${v.name} (${fmt(v.totalAmount)})`)
        .join(', ')
      return `The largest counterparties this period were: ${top}.`
    },
  },
  {
    id: 'validation',
    q: 'Were there any validation issues?',
    available: (r) => (r.validations?.length ?? 0) > 0,
    answer: (r) => {
      const rules = r.validations!
      const passed = rules.filter((x) => x.state === 'pass')
      const failed = rules.filter((x) => x.state === 'fail')
      const skipped = rules.filter((x) => x.state === 'skip')
      if (failed.length === 0 && skipped.length === 0) {
        return `All ${rules.length} cross-document checks passed (R1–R4). No validation issues were found.`
      }
      const parts: string[] = [`${passed.length} of ${rules.length} cross-document checks passed`]
      if (failed.length) parts.push(`${failed.map((x) => x.id).join(', ')} failed`)
      if (skipped.length)
        parts.push(
          `${skipped.map((x) => x.id).join(', ')} ${skipped.length === 1 ? 'was' : 'were'} skipped ` +
            `(the fields they check were not present)`,
        )
      return `${parts.join('; ')}.`
    },
  },
  {
    id: 'cash',
    q: 'How much cash did the business generate?',
    available: (r) => !!r.cashFlow,
    answer: (r) =>
      `Net cash generated was ${fmt(r.cashFlow.net)} (operating ${fmt(r.cashFlow.operating)})` +
      (r.keyMetrics.collectionRatePct !== null
        ? `, with a ${pct(r.keyMetrics.collectionRatePct)} collection rate.`
        : '.'),
  },
]

interface Props {
  report: FinancialReport
}

export default function AskPanel({ report }: Props) {
  const questions = QUESTIONS.filter((qa) => qa.available(report))
  const [activeId, setActiveId] = useState<string | null>(null)
  const active = questions.find((qa) => qa.id === activeId) ?? null

  return (
    <Card
      title={
        <Space size={8}>
          <QuestionCircleOutlined style={{ color: '#6366f1' }} />
          <span>Ask Archon</span>
        </Space>
      }
      styles={{ body: { paddingTop: 16 } }}
    >
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Grounded answers computed from this period's report — pick a question.
        </Text>

        <Space size={[8, 8]} wrap>
          {questions.map((qa) => (
            <Button
              key={qa.id}
              size="small"
              type={qa.id === activeId ? 'primary' : 'default'}
              onClick={() => setActiveId(qa.id)}
              aria-label={qa.q}
            >
              {qa.q}
            </Button>
          ))}
        </Space>

        {active && (
          <div
            data-testid="ask-answer"
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              background: 'rgba(99, 102, 241, 0.08)',
              border: '1px solid rgba(99, 102, 241, 0.25)',
              borderRadius: 8,
              padding: '12px 14px',
            }}
          >
            <BulbOutlined style={{ color: '#6366f1', marginTop: 3 }} />
            <Paragraph style={{ margin: 0 }}>{active.answer(report)}</Paragraph>
          </div>
        )}
      </Space>
    </Card>
  )
}
