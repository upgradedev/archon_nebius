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
      `a ${pct(r.pnl.operatingMarginPct)} simplified document margin.`,
  },
  {
    id: 'employer-cost',
    q: 'What employer cost does the payroll register report?',
    available: (r) => !!r.payrollGap,
    answer: (r) =>
      `The payroll register reports total employer cost of ${fmt(r.payrollGap!.trueEmployerCost)} ` +
      `across ${r.payrollGap!.employeeCount} employees. Archon uses that register value for ` +
      `payroll expense; it does not infer it from the bank transfer.`,
  },
  {
    id: 'payroll-gap',
    q: 'How do bank-confirmed net wages compare with registered employer cost?',
    available: (r) => !!r.payrollGap,
    answer: (r) => {
      const g = r.payrollGap!
      const difference = g.trueEmployerCost - g.bankTransferNet
      return (
        `The bank confirmation records ${fmt(g.bankTransferNet)} in net wages, while the ` +
        `payroll register reports ${fmt(g.trueEmployerCost)} in total employer cost — a ` +
        `${fmt(difference)} difference (${g.gapPct.toFixed(0)}%). These documents describe ` +
        `different payroll measures. Archon checks their ratio, but does not verify separate ` +
        `tax or social-insurance remittance transactions.`
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
        return `All ${rules.length} available payroll checks passed (R1–R4). This validates ` +
          `the uploaded net totals, employer-cost ratio, payment date, and headcount; it does ` +
          `not confirm separate tax or social-insurance remittances.`
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
    q: 'What cash-flow view do these documents produce?',
    available: (r) => !!r.cashFlow,
    answer: (r) =>
      `The current document-based view is ${fmt(r.cashFlow.net)} net cash ` +
      `(operating ${fmt(r.cashFlow.operating)}). It assumes sales invoices were collected and ` +
      `purchase/expense invoices were paid; generic bank-to-invoice matching is not implemented` +
      (r.keyMetrics.collectionRatePct !== null
        ? `, and the report contains a ${pct(r.keyMetrics.collectionRatePct)} collection rate.`
        : ', so collection rate is unavailable.'),
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
