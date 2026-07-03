import { useState } from 'react'
import {
  Layout, Typography, Row, Col, Card, Button, Spin, Alert, Space, theme,
  Avatar, Tooltip, Modal, Drawer, Form, Input, Popconfirm, Tag, Upload as AntUpload,
  Steps, Empty, Badge, message as antMessage, Tabs,
} from 'antd'
import {
  UploadOutlined, SettingOutlined, LogoutOutlined, DeleteOutlined,
  InboxOutlined, RocketOutlined, CheckCircleOutlined, BarChartOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import PnLChart from '../components/PnLChart'
import CashFlowChart from '../components/CashFlowChart'
import ExpenseBreakdown from '../components/ExpenseBreakdown'
import MetricsCards from '../components/MetricsCards'
import ExecutiveSummary from '../components/ExecutiveSummary'
import JobStatus from '../components/JobStatus'
import PayrollGapCard from '../components/PayrollGapCard'
import ValidationLedger from '../components/ValidationLedger'
import { isDemoMode, DEMO_PERIOD } from '../demo/demoMode'
import type { PeriodInfo, CompanyProfile } from '../types/financial'

const { Header, Content } = Layout
const { Title, Text } = Typography
const { Dragger } = AntUpload
const { useToken } = theme

const ACCEPTED_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.tif,.webp'

function fmtPeriod(p: string): string {
  const [year, month] = p.split('-')
  const d = new Date(+year, +month - 1)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
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

  // Upload flow state
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [uploadPeriod, setUploadPeriod] = useState('')
  const [uploadStep, setUploadStep] = useState(0)
  const [extractJobId, setExtractJobId] = useState<string | null>(null)
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Inline analysis trigger
  const [triggerJobId, setTriggerJobId] = useState<string | null>(null)

  const { data: periods = [], refetch: refetchPeriods } = useQuery({
    queryKey: ['periods'],
    queryFn: api.getPeriods,
    refetchInterval: 30_000,
  })

  const { data: reportData, isLoading: reportLoading, error: reportError } = useQuery({
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

  const handleUploadSubmit = async () => {
    if (fileList.length === 0) return
    setUploadError(null)
    setSubmitting(true)
    try {
      const files = fileList.map(f => f.originFileObj as File)
      // period is optional — the backend auto-detects it from the filenames and
      // returns it; use the detected value for the rest of the pipeline.
      const { uploadId, period: detectedPeriod } = await api.upload(files, uploadPeriod || undefined)
      setUploadPeriod(detectedPeriod)
      const job = await api.submitJob(uploadId, detectedPeriod)
      setExtractJobId(job.id)
      setUploadStep(1)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleExtractionComplete = async () => {
    try {
      const job = await api.analyze(uploadPeriod)
      setAnalysisJobId(job.id)
      setUploadStep(2)
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Failed to submit analysis')
      setUploadStep(0)
    }
  }

  const handleAnalysisComplete = () => {
    setUploadStep(3)
    setTimeout(() => {
      closeUploadModal()
      refetchPeriods()
      setActivePeriod(uploadPeriod)
      queryClient.invalidateQueries({ queryKey: ['report', uploadPeriod] })
    }, 1200)
  }

  const closeUploadModal = () => {
    setUploadOpen(false)
    setUploadStep(0)
    setFileList([])
    setExtractJobId(null)
    setAnalysisJobId(null)
    setUploadError(null)
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

  const activePeriodInfo: PeriodInfo | undefined = periods.find(p => p.period === activePeriod)
  const report = reportData?.report
  const needsAnalysis = activePeriodInfo?.hasExtraction && !activePeriodInfo?.hasReport

  const periodTabs = periods.map(p => ({
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
          {periods.length > 0 ? (
            <Tabs
              activeKey={activePeriod ?? undefined}
              onChange={setActivePeriod}
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
            >
              <Tooltip title="Delete period">
                <Button icon={<DeleteOutlined />} danger size="small" />
              </Tooltip>
            </Popconfirm>
          )}

          <Tooltip title="Company settings">
            <Button icon={<SettingOutlined />} size="small" onClick={openSettings} />
          </Tooltip>

          {user?.photoURL && <Avatar src={user.photoURL} size={28} />}
          <Tooltip title={user?.email}>
            <Button icon={<LogoutOutlined />} onClick={signOut} type="text" size="small" aria-label="Sign out" />
          </Tooltip>
        </Space>
      </Header>

      {/* ── Main content ── */}
      <Content style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 24px', width: '100%' }}>
        {!activePeriod ? (
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
        ) : reportLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }}>
            <Spin size="large" tip="Loading report…" />
          </div>
        ) : report ? (
          <Space direction="vertical" size={24} style={{ width: '100%' }}>
            <Row align="middle" justify="space-between">
              <Col>
                <Title level={4} style={{ margin: 0 }}>
                  {profile?.company_name || 'Financial Report'} — {fmtPeriod(activePeriod)}
                </Title>
                {reportData?.generatedAt && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Generated {new Date(reportData.generatedAt).toLocaleString()}
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

            <MetricsCards report={report} period={activePeriod} />

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
                  <PnLChart data={report.pnl} />
                </Card>
              </Col>
              <Col xs={24} lg={8}>
                <Card title="Expense Breakdown">
                  <ExpenseBreakdown data={report.expenseBreakdown} />
                </Card>
              </Col>
            </Row>

            <Row gutter={[24, 24]}>
              <Col xs={24} lg={12}>
                <Card title="Cash Flow">
                  <CashFlowChart data={report.cashFlow} />
                </Card>
              </Col>
              <Col xs={24} lg={12}>
                <Card title="Executive Summary">
                  <ExecutiveSummary summary={report.executiveSummary} period={activePeriod} />
                </Card>
              </Col>
            </Row>

            {report.validations && report.validations.length > 0 && (
              <Card
                title="Cross-document validation — R1 to R4"
                extra={<Tag color="blue">agent ledger</Tag>}
              >
                <ValidationLedger rules={report.validations} />
              </Card>
            )}
          </Space>
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
              />
            ) : (
              <Card>
                <Space direction="vertical" size={16} style={{ width: '100%', textAlign: 'center' }}>
                  <CheckCircleOutlined style={{ fontSize: 40, color: token.colorSuccess }} />
                  <Title level={5}>Extraction complete for {fmtPeriod(activePeriod)}</Title>
                  <Text type="secondary">Documents have been processed. Run the analysis pipeline to generate your P&amp;L report.</Text>
                  <Button type="primary" icon={<RocketOutlined />} onClick={triggerAnalysis}>
                    Run Analysis
                  </Button>
                </Space>
              </Card>
            )}
          </div>
        ) : reportError ? (
          <Alert
            type="warning"
            message={`No report available for ${fmtPeriod(activePeriod)}`}
            description="Upload documents and run analysis to generate a report for this period."
            action={
              <Button size="small" onClick={() => setUploadOpen(true)}>
                Upload documents
              </Button>
            }
            style={{ maxWidth: 600, margin: '60px auto' }}
          />
        ) : null}
      </Content>

      {/* ── Upload Modal ── */}
      <Modal
        open={uploadOpen}
        onCancel={closeUploadModal}
        footer={null}
        title="Upload Documents"
        width={580}
        maskClosable={uploadStep === 0}
        destroyOnHidden
      >
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          <Steps
            current={uploadStep}
            size="small"
            items={[
              { title: 'Select files' },
              { title: 'Extract' },
              { title: 'Analyse' },
              { title: 'Ready', icon: uploadStep === 3 ? <CheckCircleOutlined /> : undefined },
            ]}
          />

          {uploadStep === 0 && (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <div>
                <Text strong>Documents</Text>
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  Invoices · Payroll · Expenses · Sales
                </Text>
                <Dragger
                  multiple
                  accept={ACCEPTED_TYPES}
                  fileList={fileList}
                  beforeUpload={() => false}
                  onChange={({ fileList: fl }) => setFileList(fl)}
                  style={{ marginTop: 6 }}
                >
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p className="ant-upload-text">Drop files or click to browse</p>
                  <p className="ant-upload-hint">PDF · DOCX · JPG · PNG · TIFF — any language</p>
                </Dragger>
              </div>

              {fileList.length > 0 && (
                <Space wrap>
                  {fileList.map(f => <Tag key={f.uid} color="blue">{f.name}</Tag>)}
                </Space>
              )}

              {uploadError && <Alert type="error" message={uploadError} showIcon />}

              <Button
                type="primary"
                size="large"
                icon={<RocketOutlined />}
                block
                loading={submitting}
                disabled={fileList.length === 0}
                onClick={handleUploadSubmit}
              >
                Extract &amp; Analyse
              </Button>
            </Space>
          )}

          {uploadStep === 1 && extractJobId && (
            <JobStatus
              jobId={extractJobId}
              label="Extraction job"
              runningMessage="Processing documents with vision LLM (Qwen2.5-VL-72B)…"
              onComplete={handleExtractionComplete}
              onDismiss={closeUploadModal}
            />
          )}

          {uploadStep === 2 && analysisJobId && (
            <JobStatus
              jobId={analysisJobId}
              label="Analysis job"
              runningMessage="Running 7-agent financial analysis pipeline…"
              pollFn={api.getAnalysisJob}
              onComplete={handleAnalysisComplete}
              onDismiss={closeUploadModal}
            />
          )}

          {uploadStep === 3 && (
            <Alert type="success" message="Analysis complete — loading dashboard…" showIcon />
          )}
        </Space>
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
          <Form.Item name="company_tax_id" label="Tax ID (ΑΦΜ)">
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
