import { useState } from 'react'
import {
  Layout, Typography, Upload as AntUpload, Button,
  Steps, Card, Space, Alert, Tag, theme, Row, Col, Avatar, Tooltip,
  Table, Select, Checkbox,
} from 'antd'
import {
  InboxOutlined, RocketOutlined, CheckCircleOutlined, LogoutOutlined,
  WarningOutlined, CheckOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import JobStatus from '../components/JobStatus'
import { useAuth } from '../contexts/AuthContext'
import type { ExtractedDoc, DocType, CompanyProfile } from '../types/financial'
import { DOC_TYPE_OPTIONS } from '../types/financial'

const { Content } = Layout
const { Title, Text } = Typography
const { Dragger } = AntUpload
const { useToken } = theme

const ACCEPTED_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.tif,.webp'

// ── Entity-ownership guard ────────────────────────────────────────────────────
// Classifies each extracted document against the configured company profile so
// the user can spot documents that belong to a different entity before analysis.
type MatchStatus = 'matched' | 'unrelated' | 'unconfigured'

interface ReviewRow extends ExtractedDoc {
  _key: string
  _include: boolean
  _docType: DocType
  _status: MatchStatus
}

function docFileName(doc: ExtractedDoc): string {
  return doc.filename ?? doc.source_file ?? ''
}

function matchStatus(doc: ExtractedDoc, profile: CompanyProfile | null): MatchStatus {
  const normName = (profile?.company_name || '').trim().toLowerCase()
  const normTax = (profile?.company_tax_id || '').replace(/\D/g, '')
  if (!normName && !normTax) return 'unconfigured'
  const vendorTax = (doc.vendor_tax_id || '').replace(/\D/g, '')
  if (normTax && vendorTax && vendorTax === normTax) return 'matched'
  if (normName && (doc.vendor_name || '').toLowerCase().includes(normName)) return 'matched'
  if (normName && (doc.recipient_name || '').toLowerCase().includes(normName)) return 'matched'
  return 'unrelated'
}

export default function UploadPage() {
  const { token } = useToken()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [period, setPeriod] = useState<string>('')
  const [step, setStep] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Review step state
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([])
  const [companyProfile, setCompanyProfile] = useState<CompanyProfile | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (fileList.length === 0) return
    setError(null)
    setSubmitting(true)
    try {
      const files = fileList.map(f => f.originFileObj as File)
      // period is optional — the backend auto-detects it from the filenames and
      // returns it; use the detected value for the rest of the pipeline.
      const { uploadId, period: detectedPeriod } = await api.upload(files, period || undefined)
      setPeriod(detectedPeriod)
      const job = await api.submitJob(uploadId, detectedPeriod)
      setJobId(job.id)
      setStep(1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Extraction complete → load extracted docs + company profile → Review step.
  // (Analysis is NOT submitted here — that happens on Confirm, after review.)
  const handleExtractionComplete = async () => {
    setStep(2)
    setReviewLoading(true)
    setReviewError(null)
    try {
      const [docs, profile] = await Promise.all([
        api.getDocuments(period),
        api.getCompanyProfile(),
      ])
      setCompanyProfile(profile)
      // getDocuments returns a FLAT array of extracted documents.
      const rows: ReviewRow[] = (docs as ExtractedDoc[]).map((doc, i) => ({
        ...doc,
        _key: `${i}::${docFileName(doc)}`,
        _include: true,
        _docType: (doc.doc_type as DocType) || 'unknown',
        _status: matchStatus(doc, profile),
      }))
      setReviewRows(rows)
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : 'Failed to load documents for review')
    } finally {
      setReviewLoading(false)
    }
  }

  const updateRow = (key: string, patch: Partial<ReviewRow>) =>
    setReviewRows(prev => prev.map(r => (r._key === key ? { ...r, ...patch } : r)))

  // Confirm review → persist the approved set → THEN submit the analysis job.
  const handleConfirm = async () => {
    setConfirming(true)
    setReviewError(null)
    try {
      const approved: ExtractedDoc[] = reviewRows
        .filter(r => r._include)
        .map(({ _key, _include, _docType, _status, ...doc }) => {
          void _key; void _include; void _status
          return { ...doc, doc_type: _docType }
        })
      // Persist first so the analysis job reads only the reviewed set.
      await api.updateDocuments(period, approved)
      // Nebius analysis is a JOB: submit and poll (unlike Azure's sync /analyze).
      const analysisJob = await api.analyze(period)
      setAnalysisJobId(analysisJob.id)
      setStep(3)
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : 'Failed to start analysis')
    } finally {
      setConfirming(false)
    }
  }

  // Analysis complete → navigate to dashboard
  const handleAnalysisComplete = () => {
    setStep(4)
    setTimeout(() => navigate(`/dashboard/${period}`), 1500)
  }

  const unrelated = reviewRows.filter(r => r._status === 'unrelated')
  const included = reviewRows.filter(r => r._include)

  const REVIEW_COLUMNS = [
    {
      title: '',
      key: 'include',
      width: 36,
      render: (_: unknown, row: ReviewRow) => (
        <Checkbox
          checked={row._include}
          onChange={e => updateRow(row._key, { _include: e.target.checked })}
        />
      ),
    },
    {
      title: 'File',
      key: 'file',
      ellipsis: true,
      render: (_: unknown, row: ReviewRow) => {
        const name = docFileName(row).split('/').pop() || '—'
        return (
          <Tooltip title={name}>
            <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{name}</Text>
          </Tooltip>
        )
      },
    },
    {
      title: 'Type',
      key: 'type',
      width: 170,
      render: (_: unknown, row: ReviewRow) => (
        <Select<DocType>
          size="small"
          value={row._docType}
          onChange={v => updateRow(row._key, { _docType: v })}
          options={DOC_TYPE_OPTIONS}
          style={{ width: '100%' }}
          onClick={e => e.stopPropagation()}
        />
      ),
    },
    {
      title: 'Sender / Recipient',
      key: 'party',
      ellipsis: true,
      render: (_: unknown, row: ReviewRow) => {
        const sender = row.vendor_name
        const recipient = row.recipient_name
        return (
          <Space direction="vertical" size={0} style={{ gap: 0 }}>
            {sender && <Text style={{ fontSize: 11 }}>↑ {sender}</Text>}
            {recipient && <Text style={{ fontSize: 11 }} type="secondary">↓ {recipient}</Text>}
            {!sender && !recipient && <Text type="secondary">—</Text>}
          </Space>
        )
      },
    },
    {
      title: 'Match',
      key: 'status',
      width: 90,
      render: (_: unknown, row: ReviewRow) => {
        if (row._status === 'matched')
          return <Tag color="green" icon={<CheckOutlined />} style={{ fontSize: 10 }}>Matched</Tag>
        if (row._status === 'unrelated')
          return <Tag color="orange" icon={<WarningOutlined />} style={{ fontSize: 10 }}>Review</Tag>
        return <Tag color="default" style={{ fontSize: 10 }}>—</Tag>
      },
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }}>
      <Content style={{ maxWidth: 800, margin: '0 auto', padding: '48px 24px' }}>
        <Space direction="vertical" size={32} style={{ width: '100%' }}>
          <Row align="middle" justify="space-between">
            <Col>
              <Title level={2} style={{ margin: 0 }}>Archon</Title>
              <Text type="secondary">Agentic Financial Intelligence — upload documents, get P&amp;L insights</Text>
            </Col>
            <Col>
              <Space>
                {user?.photoURL && <Avatar src={user.photoURL} size={32} />}
                <Tooltip title={user?.email}>
                  <Button icon={<LogoutOutlined />} onClick={signOut} type="text">
                    Sign out
                  </Button>
                </Tooltip>
              </Space>
            </Col>
          </Row>

          <Steps
            current={step}
            items={[
              { title: 'Upload documents' },
              { title: 'Extract data' },
              { title: 'Review' },
              { title: 'Analyse' },
              { title: 'Ready', icon: step === 4 ? <CheckCircleOutlined /> : undefined },
            ]}
          />

          {step === 0 && (
            <Card>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>

                <div>
                  <Text strong>Documents</Text>
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    Invoices · Payroll · Expenses · Sales — any language
                  </Text>
                  <Dragger
                    multiple
                    accept={ACCEPTED_TYPES}
                    fileList={fileList}
                    beforeUpload={() => false}
                    onChange={({ fileList: fl }) => setFileList(fl)}
                    style={{ marginTop: 8 }}
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">
                      Drop files here or click to browse
                    </p>
                    <p className="ant-upload-hint">
                      PDF · DOCX · JPG · PNG · TIFF — scanned or digital, any language
                    </p>
                  </Dragger>
                </div>

                {fileList.length > 0 && (
                  <Space wrap>
                    {fileList.map(f => (
                      <Tag key={f.uid} color="blue">{f.name}</Tag>
                    ))}
                  </Space>
                )}

                {error && <Alert type="error" message={error} showIcon />}

                <Button
                  type="primary"
                  size="large"
                  icon={<RocketOutlined />}
                  block
                  loading={submitting}
                  disabled={fileList.length === 0}
                  onClick={handleSubmit}
                >
                  Extract & Analyse
                </Button>
              </Space>
            </Card>
          )}

          {step === 1 && jobId && (
            <JobStatus
              jobId={jobId}
              label="Extraction job"
              runningMessage="Processing documents with vision LLM (Qwen2.5-VL-72B)…"
              onComplete={handleExtractionComplete}
            />
          )}

          {/* ── Step 2: document review + entity-ownership guard ─────────── */}
          {step === 2 && (
            <Card title="Review extracted documents" loading={reviewLoading}>
              {!reviewLoading && (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  {companyProfile && !companyProfile.company_name && !companyProfile.company_tax_id && (
                    <Alert
                      type="warning"
                      showIcon
                      message="Company profile not configured"
                      description="Set your company name and tax ID in the company profile to enable automatic document matching."
                    />
                  )}

                  {unrelated.length > 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      icon={<WarningOutlined />}
                      message={`${unrelated.length} document${unrelated.length !== 1 ? 's' : ''} may not belong to ${companyProfile?.company_name || 'your company'}`}
                      description="Review the highlighted rows. Uncheck any document you want to exclude from analysis."
                    />
                  )}

                  {reviewError && <Alert type="error" message={reviewError} showIcon />}

                  <Table<ReviewRow>
                    size="small"
                    pagination={false}
                    columns={REVIEW_COLUMNS}
                    dataSource={reviewRows}
                    rowKey={r => r._key}
                    rowClassName={r => (r._status === 'unrelated' && r._include ? 'row-warn' : '')}
                    scroll={{ x: 560 }}
                  />

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {included.length} of {reviewRows.length} document{reviewRows.length !== 1 ? 's' : ''} will be analysed
                    </Text>
                    <Button
                      type="primary"
                      loading={confirming}
                      disabled={included.length === 0}
                      onClick={handleConfirm}
                      icon={<ThunderboltOutlined />}
                    >
                      Confirm & Run Analysis
                    </Button>
                  </div>
                </Space>
              )}
            </Card>
          )}

          {step === 3 && analysisJobId && (
            <JobStatus
              jobId={analysisJobId}
              label="Analysis job"
              runningMessage="Running 7-agent financial analysis pipeline…"
              pollFn={api.getAnalysisJob}
              onComplete={handleAnalysisComplete}
            />
          )}

          {step === 4 && (
            <Alert
              type="success"
              message="Analysis complete — loading dashboard…"
              showIcon
            />
          )}
        </Space>
      </Content>
    </Layout>
  )
}
