import { useState } from 'react'
import {
  Layout, Typography, Row, Col, Card, Button, Spin, Alert, Space, theme,
  Avatar, Tooltip, Modal, Drawer, Form, Input, Popconfirm, Tag,
  Empty, Badge, message as antMessage, Tabs,
} from 'antd'
import {
  UploadOutlined, SettingOutlined, LogoutOutlined, DeleteOutlined,
  RocketOutlined, CheckCircleOutlined, BarChartOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import UploadPage from './Upload'
import PnLChart from '../components/PnLChart'
import CashFlowChart from '../components/CashFlowChart'
import ExpenseBreakdown from '../components/ExpenseBreakdown'
import MetricsCards from '../components/MetricsCards'
import ExecutiveSummary from '../components/ExecutiveSummary'
import AskPanel from '../components/AskPanel'
import JobStatus from '../components/JobStatus'
import PayrollGapCard from '../components/PayrollGapCard'
import ValidationLedger from '../components/ValidationLedger'
import ErrorBoundary from '../components/ErrorBoundary'
import ColdStartOverlay from '../components/ColdStartOverlay'
import { isDemoMode, DEMO_PERIOD } from '../demo/demoMode'
import { DEMO_REPORT, DEMO_PERIODS, DEMO_PROFILE, DEMO_DOCUMENTS } from '../demo/demoData'
import type { PeriodInfo, CompanyProfile } from '../types/financial'

const { Header, Content } = Layout
const { Title, Text } = Typography
const { useToken } = theme

function fmtPeriod(p: string): string {
  const [year, month] = p.split('-')
  const d = new Date(+year, +month - 1)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

// Best-effort HTTP status extraction from a thrown query error, so the report
// panel can distinguish a genuine 404 (no report yet) from a real 5xx/network
// failure. Returns undefined for non-HTTP errors.
function errorStatus(e: unknown): number | undefined {
  if (e && typeof e === 'object' && 'response' in e) {
    return (e as { response?: { status?: number } }).response?.status
  }
  return undefined
}

export default function Dashboard() {
  const { token } = useToken()
  const { user, signOut } = useAuth()
  const queryClient = useQueryClient()

  // Demo mode auto-selects the seeded period so the dashboard renders straight
  // away (no auth, no clicks) for the beat-aligned demo-video tour.
  const [activePeriod, setActivePeriod] = useState<string | null>(
    isDemoMode() ? DEMO_PERIOD : null,
  )
  const [uploadOpen, setUploadOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Inline analysis trigger (dashboard "Run Analysis" for an extracted-only period)
  const [triggerJobId, setTriggerJobId] = useState<string | null>(null)

  const { data: periods = [], refetch: refetchPeriods, isLoading: periodsLoading } = useQuery({
    queryKey: ['periods'],
    queryFn: api.getPeriods,
    refetchInterval: 30_000,
  })

  const { data: reportData, isLoading: reportLoading, error: reportError, refetch: refetchReport } = useQuery({
    queryKey: ['report', activePeriod],
    queryFn: () => api.getReport(activePeriod!),
    enabled: !!activePeriod,
    retry: false,
  })

  const { data: profile } = useQuery({
    queryKey: ['company-profile'],
    queryFn: api.getCompanyProfile,
  })

  const deletePeriod = useMutation({
    mutationFn: (p: string) => api.deletePeriod(p),
    onSuccess: (_, p) => {
      if (activePeriod === p) setActivePeriod(null)
      queryClient.invalidateQueries({ queryKey: ['periods'] })
      queryClient.invalidateQueries({ queryKey: ['report', p] })
      antMessage.success(`Period ${fmtPeriod(p)} deleted`)
    },
    onError: () => antMessage.error('Delete failed'),
  })

  const updateProfile = useMutation({
    mutationFn: (vals: CompanyProfile) => api.updateCompanyProfile(vals),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-profile'] })
      antMessage.success('Profile saved')
      setSettingsOpen(false)
    },
  })

  const [profileForm] = Form.useForm<CompanyProfile>()

  // The upload flow lives entirely in the shared <UploadPage> component (also the
  // standalone page). The modal just hosts it; on completion the component hands
  // back the resolved period so the dashboard can refresh and select it.
  const closeUploadModal = () => setUploadOpen(false)

  const handleUploadComplete = (period: string) => {
    setUploadOpen(false)
    refetchPeriods()
    queryClient.invalidateQueries({ queryKey: ['periods'] })
    queryClient.invalidateQueries({ queryKey: ['report', period] })
    queryClient.invalidateQueries({ queryKey: ['documents', period] })
    setActivePeriod(period)
  }

  const openSettings = () => {
    profileForm.setFieldsValue(profile ?? { company_name: '', company_tax_id: '' })
    setSettingsOpen(true)
  }

  const triggerAnalysis = async () => {
    if (!activePeriod) return
    try {
      const job = await api.analyze(activePeriod)
      setTriggerJobId(job.id)
    } catch (err) {
      antMessage.error(err instanceof Error ? err.message : 'Failed to start analysis')
    }
  }

  const demo = isDemoMode()

  // ── Sample-data fallback ──────────────────────────────────────────────────────
  // A SIGNED-IN visitor whose store is empty (no periods) would otherwise land on
  // a blank dashboard — a poor first impression, especially after a store purge.
  // In that case we render the SAME shared sample dataset the ?demo=1 path uses,
  // with a clear banner. Distinct from demo mode (which is always-on via the URL):
  // this triggers ONLY on an empty real store for an authenticated user and drops
  // the instant they select or upload a real period. Pure client-side — nothing is
  // written to the backend.
  const sampleFallback =
    !demo && !!user && !periodsLoading && periods.length === 0 && !activePeriod

  // `useSample` = the dashboard is showing the shared sample dataset (either path).
  const useSample = demo || sampleFallback

  // Effective render values. Demo keeps its existing data flow (fixtures arrive via
  // the api client); the fallback injects the fixtures here since its api calls
  // return the real — empty — store.
  const effectivePeriod = activePeriod ?? (sampleFallback ? DEMO_PERIOD : null)
  const effectivePeriods = sampleFallback ? DEMO_PERIODS : periods
  const report = reportData?.report ?? (sampleFallback ? DEMO_REPORT.report : undefined)
  const reportGeneratedAt =
    reportData?.generatedAt ?? (sampleFallback ? DEMO_REPORT.generatedAt : undefined)
  const effectiveProfile = sampleFallback ? DEMO_PROFILE : profile

  const activePeriodInfo: PeriodInfo | undefined =
    effectivePeriods.find(p => p.period === effectivePeriod)
  const needsAnalysis = activePeriodInfo?.hasExtraction && !activePeriodInfo?.hasReport

  const periodTabs = effectivePeriods.map(p => ({
    key: p.period,
    label: (
      <Space size={6}>
        {fmtPeriod(p.period)}
        {p.hasReport
          ? <Badge status="success" />
          : p.hasExtraction
            ? <Badge status="processing" />
            : <Badge status="default" />}
      </Space>
    ),
  }))

  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }}>
      {/* ── Header ── */}
      <Header
        style={{
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <Space size={4} style={{ flexShrink: 0 }}>
          <BarChartOutlined style={{ fontSize: 20, color: token.colorPrimary }} />
          <Title level={5} style={{ margin: 0 }}>Archon</Title>
        </Space>

        {/* Period tabs */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {effectivePeriods.length > 0 ? (
            <Tabs
              activeKey={effectivePeriod ?? undefined}
              // In the sample fallback the single tab is the seeded sample — selecting
              // it must not kick off a real report fetch, so the change is a no-op there.
              onChange={(k) => { if (!sampleFallback) setActivePeriod(k) }}
              items={periodTabs}
              style={{ marginBottom: 0 }}
              tabBarStyle={{ marginBottom: 0, border: 'none' }}
              size="small"
            />
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>No periods yet — upload documents to get started</Text>
          )}
        </div>

        {/* Actions */}
        <Space style={{ flexShrink: 0 }}>
          <Button
            type="primary"
            icon={<UploadOutlined />}
            onClick={() => setUploadOpen(true)}
            size="small"
          >
            Upload
          </Button>

          {activePeriod && (
            <Tooltip title="Refresh this period">
              <Button
                icon={<ReloadOutlined />}
                size="small"
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ['periods'] })
                  queryClient.invalidateQueries({ queryKey: ['report', activePeriod] })
                  queryClient.invalidateQueries({ queryKey: ['documents', activePeriod] })
                  antMessage.success('Refreshed')
                }}
                aria-label="Refresh period"
              />
            </Tooltip>
          )}

          {activePeriod && (
            <Popconfirm
              title={`Delete period ${fmtPeriod(activePeriod)}?`}
              description="This removes all uploaded files, extracted data, and the report."
              onConfirm={() => deletePeriod.mutate(activePeriod)}
              okText="Delete"
              okButtonProps={{ danger: true }}
              disabled={!!triggerJobId || deletePeriod.isPending}
            >
              <Tooltip title={triggerJobId ? 'Analysis running — cannot delete' : 'Delete period'}>
                <Button
                  icon={<DeleteOutlined />}
                  danger
                  size="small"
                  disabled={!!triggerJobId || deletePeriod.isPending}
                  aria-label="Delete period"
                />
              </Tooltip>
            </Popconfirm>
          )}

          <Tooltip title="Company settings">
            <Button icon={<SettingOutlined />} size="small" onClick={openSettings} aria-label="Company settings" />
          </Tooltip>

          {user?.photoURL && <Avatar src={user.photoURL} size={28} />}
          <Tooltip title={user?.email}>
            <Button icon={<LogoutOutlined />} onClick={signOut} type="text" size="small" aria-label="Sign out" />
          </Tooltip>
        </Space>
      </Header>

      {/* ── Main content ── */}
      <Content style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 24px', width: '100%' }}>
        {/* Honest banner whenever the dashboard is showing the shared sample data
            — either the ?demo=1 tour or the signed-in empty-store fallback. */}
        {useSample && (
          <Alert
            type="info"
            banner
            showIcon
            message={
              sampleFallback
                ? 'Demo dataset — this is a shared sample. Upload your own documents to analyse them.'
                : 'Demo mode — this is a sample dashboard. Sign in to analyse your own documents.'
            }
            style={{ marginBottom: 20 }}
          />
        )}
        {!effectivePeriod ? (
          periodsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }}>
              <Spin size="large" />
            </div>
          ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" size={12} style={{ textAlign: 'center' }}>
                <Text>No period selected</Text>
                <Text type="secondary">Upload documents to create your first financial period</Text>
                <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
                  Upload documents
                </Button>
              </Space>
            }
            style={{ marginTop: 80 }}
          />
          )
        ) : reportLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }}>
            <Spin size="large" tip="Loading report…" />
          </div>
        ) : report ? (
          <ErrorBoundary>
          <Space direction="vertical" size={24} style={{ width: '100%' }}>
            <Row align="middle" justify="space-between">
              <Col>
                <Title level={4} style={{ margin: 0 }}>
                  {effectiveProfile?.company_name || 'Financial Report'} — {fmtPeriod(effectivePeriod!)}
                </Title>
                {reportGeneratedAt && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Generated {new Date(reportGeneratedAt).toLocaleString()}
                  </Text>
                )}
              </Col>
              <Col>
                <Space>
                  {activePeriodInfo?.hasExtraction && (
                    <Tag color="green">Extraction complete</Tag>
                  )}
                  <Tag color="blue">Report ready</Tag>
                </Space>
              </Col>
            </Row>

            {report.pnl && report.keyMetrics && (
              <MetricsCards
                report={report}
                period={effectivePeriod!}
                documents={sampleFallback ? DEMO_DOCUMENTS : undefined}
              />
            )}

            {/* Executive summary is the "30-second" headline for a reader — kept at
                the TOP, directly under the KPI tiles, paired with the scoped Q&A.
                Both stack to full width below the lg breakpoint. */}
            <Row gutter={[24, 24]}>
              <Col xs={24} lg={15}>
                <Card title="Executive Summary">
                  <ExecutiveSummary summary={report.executiveSummary} period={effectivePeriod!} />
                </Card>
              </Col>
              <Col xs={24} lg={9}>
                <AskPanel report={report} />
              </Col>
            </Row>

            {report.payrollGap && (
              <Card
                title="Payroll — bank net vs true employer cost"
                extra={<Tag color="green">3-document fusion</Tag>}
              >
                <PayrollGapCard gap={report.payrollGap} />
              </Card>
            )}

            <Row gutter={[24, 24]}>
              <Col xs={24} lg={16}>
                <Card title="Revenue vs Expenses vs Net Profit">
                  {report.pnl
                    ? <PnLChart data={report.pnl} />
                    : <Empty description="No P&L data" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card title="Expense Breakdown">
                  {report.expenseBreakdown?.length
                    ? <ExpenseBreakdown data={report.expenseBreakdown} />
                    : <Empty description="No expense data" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                </Card>
              </Col>
            </Row>

            <Card title="Cash Flow">
              {report.cashFlow
                ? <CashFlowChart data={report.cashFlow} />
                : <Empty description="No cash-flow data" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            </Card>

            {report.validations && report.validations.length > 0 && (
              <Card
                title="Cross-document validation — R1 to R4"
                extra={<Tag color="blue">agent ledger</Tag>}
              >
                <ValidationLedger rules={report.validations} />
              </Card>
            )}
          </Space>
          </ErrorBoundary>
        ) : needsAnalysis ? (
          <div style={{ maxWidth: 480, margin: '80px auto' }}>
            {triggerJobId ? (
              <JobStatus
                jobId={triggerJobId}
                label="Analysis job"
                runningMessage="Running 7-agent financial analysis pipeline…"
                pollFn={api.getAnalysisJob}
                onComplete={() => {
                  setTriggerJobId(null)
                  refetchPeriods()
                  queryClient.invalidateQueries({ queryKey: ['report', activePeriod] })
                }}
                onDismiss={() => setTriggerJobId(null)}
              />
            ) : (
              <Card>
                <Space direction="vertical" size={16} style={{ width: '100%', textAlign: 'center' }}>
                  <CheckCircleOutlined style={{ fontSize: 40, color: token.colorSuccess }} />
                  <Title level={5}>Extraction complete for {fmtPeriod(effectivePeriod!)}</Title>
                  <Text type="secondary">Documents have been processed. Run the analysis pipeline to generate your P&amp;L report.</Text>
                  <Button type="primary" icon={<RocketOutlined />} onClick={triggerAnalysis}>
                    Run Analysis
                  </Button>
                </Space>
              </Card>
            )}
          </div>
        ) : reportError ? (
          errorStatus(reportError) === 404 ? (
            <Alert
              type="warning"
              message={`No report available for ${fmtPeriod(effectivePeriod!)}`}
              description="Upload documents and run analysis to generate a report for this period."
              action={
                <Button size="small" onClick={() => setUploadOpen(true)}>
                  Upload documents
                </Button>
              }
              style={{ maxWidth: 600, margin: '60px auto' }}
            />
          ) : errorStatus(reportError) === 502 || errorStatus(reportError) === 503 ? (
            // Cold start: DON'T dump to a red error screen. Show a calm "warming up"
            // state — the ColdStartOverlay is already auto-retrying /api/health and
            // will refetch this report automatically once the endpoint is warm.
            <Alert
              type="info"
              showIcon
              icon={<Spin />}
              message="Nebius endpoint is starting up"
              description="This can take ~5 minutes on first use. The report will load automatically once it's warm — no need to retry."
              style={{ maxWidth: 600, margin: '60px auto' }}
            />
          ) : (
            <Alert
              type="error"
              showIcon
              message={`Couldn't load the report for ${fmtPeriod(effectivePeriod!)}`}
              description="The service may be starting up or briefly unavailable. Please try again."
              action={
                <Button size="small" icon={<ReloadOutlined />} onClick={() => refetchReport()}>
                  Retry
                </Button>
              }
              style={{ maxWidth: 600, margin: '60px auto' }}
            />
          )
        ) : null}
      </Content>

      {/* Cold-start recovery — a fixed, non-blocking banner that auto-retries the
          Nebius endpoint until warm. Never blanks the view. */}
      <ColdStartOverlay />

      {/* ── Upload Modal ──
          Hosts the SINGLE shared upload flow (<UploadPage>, also the standalone
          page). The embedded variant drops its own Layout/header and calls
          onComplete(period) when analysis finishes — see pages/Upload.tsx. Wide,
          scrollable body so the Review-step table fits. */}
      <Modal
        open={uploadOpen}
        onCancel={closeUploadModal}
        footer={null}
        title="Upload Documents"
        width={Math.min(window.innerWidth - 40, 860)}
        styles={{ body: { maxHeight: '80vh', overflowY: 'auto' } }}
        destroyOnHidden
      >
        <UploadPage onComplete={handleUploadComplete} />
      </Modal>

      {/* ── Company Profile Drawer ── */}
      <Drawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title="Company Settings"
        width={360}
      >
        <Form
          form={profileForm}
          layout="vertical"
          onFinish={vals => updateProfile.mutate(vals)}
        >
          <Form.Item name="company_name" label="Company Name">
            <Input placeholder="Acme Ltd" />
          </Form.Item>
          <Form.Item name="company_tax_id" label="Tax ID">
            <Input placeholder="123456789" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            loading={updateProfile.isPending}
          >
            Save
          </Button>
        </Form>
      </Drawer>
    </Layout>
  )
}
