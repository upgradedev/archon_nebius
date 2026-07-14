import { useState } from 'react'
import { Row, Col, Card, Statistic, Tag, Modal, Typography, Tooltip, Table, Spin } from 'antd'
import {
  ArrowUpOutlined, ArrowDownOutlined,
  EuroOutlined, FileTextOutlined, PercentageOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import type { FinancialReport, ExtractedDoc } from '../types/financial'
import { api } from '../api/client'

const { Text } = Typography

interface Props {
  report: FinancialReport
  period: string
  // When provided, the tile drill-down uses these documents directly instead of
  // fetching them — used by the signed-in empty-store sample fallback so no
  // /api/documents call is made for the seeded dataset.
  documents?: ExtractedDoc[]
}

const fmt = (v: number) =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

// Plain-English definition shown on the (i) icon of each tile. Universal
// terminology only — no jurisdiction-specific tax terms.
const TILE_TOOLTIPS: Record<string, string> = {
  'Revenue': 'Net revenue excluding VAT from sales invoices issued by the company. VAT is excluded — it is collected on behalf of the tax authority.',
  'Net Profit': 'Revenue (ex-VAT) minus total expenses. Positive means a profitable period; negative means a loss.',
  'Gross Margin': 'Gross profit as a share of revenue — how much of each unit of revenue remains after direct costs.',
  'Revenue Growth': 'Change in revenue versus the prior period.',
  'Invoices': 'Total financial documents processed: sales invoices, purchase invoices and expense receipts.',
  'Collection Rate': 'Share of invoiced revenue collected in cash during the period.',
}

// Which document types back each drillable tile — a tile is clickable iff it has
// an entry here (Revenue Growth has none, so it stays informational). Values are
// plain strings compared against `doc_type`, so no dependency on the DocType union.
const TILE_DOC_TYPES: Record<string, string[]> = {
  'Revenue': ['sales'],
  'Net Profit': ['sales', 'invoice', 'expense', 'payroll', 'payroll_register', 'payslip', 'bank_confirmation'],
  'Gross Margin': ['sales', 'invoice', 'expense', 'payroll', 'payroll_register', 'payslip'],
  'Collection Rate': ['sales', 'bank_confirmation'],
  'Invoices': ['sales', 'invoice', 'expense'],
}

// Contextual empty state per tile — explains WHY no docs matched, not just "none".
const TILE_EMPTY_TEXT: Record<string, string> = {
  'Revenue': 'No sales invoices found. Set your company name and tax ID in Settings so the classifier can identify your sales documents.',
  'Collection Rate': 'No sales or bank documents found. Set your company name and tax ID in Settings so collections can be matched.',
}
const DEFAULT_EMPTY = 'No supporting documents found for this metric.'

// Universal doc-type presentation (labels + colours) — no jurisdiction terms.
const DOC_COLOR: Record<string, string> = {
  sales: 'green', invoice: 'orange', expense: 'red',
  payroll: 'purple', payroll_register: 'purple', payslip: 'purple',
  bank_confirmation: 'blue', account_statement: 'cyan', unknown: 'default',
}
const DOC_LABEL: Record<string, string> = {
  sales: 'Sales Invoice', invoice: 'Purchase Invoice', expense: 'Expense',
  payroll: 'Payroll', payroll_register: 'Payroll Register', payslip: 'Payslip',
  bank_confirmation: 'Bank Statement', account_statement: 'Account Statement', unknown: 'Unknown',
}

const dash = <Text type="secondary" style={{ fontSize: 11 }}>—</Text>

// Columns for the drill-down document table. Every field is optional on
// ExtractedDoc, so each cell null-guards.
const DOC_COLUMNS = [
  {
    title: 'File', key: 'source_file',
    render: (_: unknown, d: ExtractedDoc) => {
      const name = (d.source_file ?? d.filename ?? '').split('/').pop() || '—'
      return <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{name}</Text>
    },
  },
  {
    title: 'Type', dataIndex: 'doc_type', key: 'doc_type',
    render: (v: string) => <Tag color={DOC_COLOR[v] ?? 'default'} style={{ fontSize: 10 }}>{DOC_LABEL[v] ?? v}</Tag>,
  },
  {
    title: 'Doc #', dataIndex: 'invoice_number', key: 'invoice_number',
    render: (v?: string) => v ?? dash,
  },
  {
    title: 'Counterparty', key: 'counterparty',
    render: (_: unknown, d: ExtractedDoc) => d.vendor_name ?? d.recipient_name ?? dash,
  },
  {
    title: 'Date', dataIndex: 'issue_date', key: 'issue_date',
    render: (v?: string) => v ?? <Tag color="warning" style={{ fontSize: 10 }}>Not detected</Tag>,
  },
  {
    title: 'Total', dataIndex: 'total_amount', key: 'total_amount', align: 'right' as const,
    render: (v: number | undefined, d: ExtractedDoc) =>
      v != null
        ? <span style={{ color: d.doc_type === 'sales' ? '#22c55e' : '#f43f5e' }}>{fmt(v)}</span>
        : dash,
  },
  {
    title: 'Confidence', dataIndex: 'confidence', key: 'confidence',
    render: (v?: number) => <Text type="secondary" style={{ fontSize: 11 }}>{v != null ? `${(v * 100).toFixed(0)}%` : '—'}</Text>,
  },
]

// Tiles that drill into their supporting documents. Purely-informational tiles
// (Revenue Growth) have no doc-type mapping and stay non-interactive — they still
// carry a definition tooltip.
export default function MetricsCards({ report, period, documents }: Props) {
  const { keyMetrics: metrics, pnl } = report
  const growthPositive = (metrics.revenueGrowthPct ?? 0) >= 0
  const [activeTile, setActiveTile] = useState<string | null>(null)

  const isDrillable = (label: string): boolean => label in TILE_DOC_TYPES

  // Fetch the period's extracted documents once a tile is open. Nebius returns a
  // FLAT ExtractedDoc[] (not Azure's { documents }). In demo mode api.getDocuments
  // serves the seeded document set client-side (no backend), so the drill-down is
  // populated for a judge exactly as it is against a real report.
  const { data: docsRaw = [], isLoading: docsFetching } = useQuery({
    queryKey: ['documents', period],
    queryFn: () => api.getDocuments(period),
    enabled: !!activeTile && !!period && documents === undefined,
    retry: false,
  })
  // Prefer an injected document set (sample fallback); otherwise use the fetched,
  // shape-normalised ExtractedDoc[]. Loading only applies to the fetch path.
  const allDocs = documents ?? docsRaw
  const docsLoading = documents === undefined && docsFetching
  const tileDocs = activeTile
    ? allDocs.filter(d => TILE_DOC_TYPES[activeTile]?.includes(d.doc_type))
    : []

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

  // Tile title with a definition tooltip. The (i) icon stops propagation so a
  // click on it reveals the definition without also opening the drill-down.
  const tileTitle = (label: string) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      {label}
      {TILE_TOOLTIPS[label] && (
        <Tooltip title={TILE_TOOLTIPS[label]} placement="top">
          <InfoCircleOutlined
            style={{ fontSize: 11, color: '#8c8c8c' }}
            onClick={e => e.stopPropagation()}
            aria-label={`${label} — definition`}
          />
        </Tooltip>
      )}
    </span>
  )

  return (
    <>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Revenue')}>
            <Statistic
              title={tileTitle('Revenue')}
              value={pnl.revenue}
              formatter={v => fmt(Number(v))}
              prefix={<EuroOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Net Profit')}>
            <Statistic
              title={tileTitle('Net Profit')}
              value={pnl.netProfit}
              formatter={v => fmt(Number(v))}
              valueStyle={{ color: pnl.netProfit >= 0 ? '#22c55e' : '#f43f5e' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Gross Margin')}>
            <Statistic
              title={tileTitle('Gross Margin')}
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
            {metrics.revenueGrowthPct === null ? (
              <Statistic
                title={tileTitle('Revenue Growth')}
                value="—"
                valueStyle={{ color: '#64748b' }}
              />
            ) : (
              <Statistic
                title={tileTitle('Revenue Growth')}
                value={Math.abs(metrics.revenueGrowthPct)}
                precision={1}
                suffix="%"
                prefix={growthPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                valueStyle={{ color: growthPositive ? '#22c55e' : '#f43f5e' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small" {...tileProps('Invoices')}>
            <Statistic
              title={tileTitle('Invoices')}
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
            {metrics.collectionRatePct === null ? (
              <Statistic
                title={tileTitle('Collection Rate')}
                value="—"
                valueStyle={{ color: '#64748b' }}
              />
            ) : (
              <Statistic
                title={tileTitle('Collection Rate')}
                value={metrics.collectionRatePct}
                precision={1}
                suffix="%"
                valueStyle={{ color: metrics.collectionRatePct >= 90 ? '#22c55e' : '#f97316' }}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* Tile drill-down — lists the documents that support the clicked metric,
          filtered to the relevant doc types. Data comes from the existing
          getDocuments(period) client method — no new backend. */}
      <Modal
        open={!!activeTile}
        title={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <FileTextOutlined style={{ color: '#6366f1' }} />
            {activeTile ? `${activeTile} — supporting documents` : ''}
          </span>
        }
        onCancel={() => setActiveTile(null)}
        footer={null}
        width={Math.min(typeof window !== 'undefined' ? window.innerWidth - 48 : 900, 900)}
        destroyOnHidden
      >
        {activeTile && (
          <>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {TILE_TOOLTIPS[activeTile]}
            </Text>
            <div style={{ marginTop: 12 }}>
              {docsLoading ? (
                <div style={{ textAlign: 'center', padding: 32 }}>
                  <Spin tip="Loading documents…">
                    <div style={{ height: 40 }} />
                  </Spin>
                </div>
              ) : (
                <Table
                  size="small"
                  pagination={{ pageSize: 20, size: 'small' }}
                  columns={DOC_COLUMNS}
                  dataSource={tileDocs}
                  rowKey={d => d.source_file ?? d.filename ?? d.invoice_number ?? JSON.stringify(d)}
                  locale={{ emptyText: TILE_EMPTY_TEXT[activeTile] ?? DEFAULT_EMPTY }}
                  scroll={{ x: 760 }}
                />
              )}
            </div>
          </>
        )}
      </Modal>
    </>
  )
}
