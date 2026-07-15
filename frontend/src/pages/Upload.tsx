import { useState, useEffect, useMemo, useRef } from 'react'
import {
  Layout, Typography, Upload as AntUpload, Button,
  Steps, Card, Space, Alert, Tag, theme, Row, Col, Avatar, Tooltip,
  Table, Select, Checkbox, Progress, Spin,
} from 'antd'
import {
  InboxOutlined, RocketOutlined, CheckCircleOutlined, LogoutOutlined,
  WarningOutlined, CheckOutlined, ThunderboltOutlined,
  EditOutlined, CalendarOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import JobStatus from '../components/JobStatus'
import { useAuth } from '../contexts/AuthContext'
import { isDemoMode } from '../demo/demoMode'
import type { ExtractedDoc, DocType, CompanyProfile } from '../types/financial'
import { DOC_TYPE_OPTIONS } from '../types/financial'

const { Content } = Layout
const { Title, Text } = Typography
const { Dragger } = AntUpload
const { useToken } = theme

const ACCEPTED_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.tif,.webp'
const MONTH_NAMES = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
]

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

// Client-side fallback-period detection from filenames. This is purely a UI
// convenience over the EXISTING optional-period upload API — each document's own
// date still takes priority server-side; this value is used only where no date
// is found.
function detectPeriodFromFiles(files: UploadFile[]): string {
  for (const file of files) {
    const name = (file.name || '').toLowerCase()
    const m = name.match(/(\d{4})[-_](0[1-9]|1[0-2])/)
    if (m) return `${m[1]}-${m[2]}`
    for (let i = 0; i < MONTH_NAMES.length; i++) {
      if (name.includes(MONTH_NAMES[i])) {
        const ym = name.match(/(\d{4})/)
        if (ym) {
          const year = Number(ym[1])
          if (year >= 2020 && year <= new Date().getFullYear() + 1) {
            return `${ym[1]}-${String(i + 1).padStart(2, '0')}`
          }
        }
      }
    }
  }
  const d = new Date()
  d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function fmtPeriod(p: string) {
  const [y, m] = p.split('-')
  return new Date(Number(y), Number(m) - 1).toLocaleString('en-GB', { month: 'long', year: 'numeric' })
}

interface UploadPageProps {
  // When provided, UploadPage renders as an embeddable component (no page header,
  // no outer Layout) and calls onComplete(period) after analysis finishes — used
  // by the Dashboard upload modal. When absent, it renders as a full standalone
  // page and navigates to the dashboard on completion.
  onComplete?: (period: string) => void
}

export default function UploadPage({ onComplete }: UploadPageProps = {}) {
  const { token } = useToken()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  // Demo mode runs a pre-loaded SAMPLE document set through the pipeline UI; the
  // user's own file is not processed. We surface that plainly on the upload and
  // review steps so the seeded rows are never mistaken for the user's upload.
  const demo = isDemoMode()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [period, setPeriod] = useState<string>('')
  const [editingPeriod, setEditingPeriod] = useState(false)
  const [step, setStep] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  // Upload lifecycle the user can actually see:
  //   'warming'    = the endpoint was cold; we poll /api/health and only write
  //                  once it answers, so the write never dies mid-cold-start.
  //   'sending'    = bytes uploading (deterministic % bar).
  //   'processing' = bytes are in, waiting on the server (store + submit the job).
  // This means the user is never left staring at a frozen "Uploading…" or an
  // unexplained "warming up" while a scaled-to-zero endpoint starts.
  const [uploadPhase, setUploadPhase] = useState<'warming' | 'sending' | 'processing'>('sending')
  const [warmWaited, setWarmWaited] = useState(0)
  // Holds the post-analysis redirect timer so it can be cleared on unmount — the
  // Dashboard modal unmounts this component the instant analysis completes.
  const completeTimerRef = useRef<number | null>(null)

  // Review step state
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([])
  const [companyProfile, setCompanyProfile] = useState<CompanyProfile | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  // Auto-detect a fallback period from the selected filenames.
  useEffect(() => {
    if (fileList.length > 0) setPeriod(detectPeriodFromFiles(fileList))
  }, [fileList])

  // Clear the pending redirect timer if the component unmounts first.
  useEffect(() => () => {
    if (completeTimerRef.current !== null) window.clearTimeout(completeTimerRef.current)
  }, [])

  // Last 24 months for the period Select, capped at the current month.
  const PERIOD_OPTIONS = useMemo(() => {
    const now = new Date()
    return Array.from({ length: 24 }, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      return { value: val, label: fmtPeriod(val) }
    })
  }, [])

  const handleSubmit = async () => {
    if (fileList.length === 0) return
    setError(null)
    setSubmitting(true)
    setUploadPct(0)
    setWarmWaited(0)
    setUploadPhase('sending')

    const files = fileList.map(f => f.originFileObj as File)
    const fileNames = fileList.map(f => f.name)
    const startedAt = Date.now()
    const MAX_MS = 6 * 60_000

    // A scaled-to-zero endpoint answers 502/503 (incl. ADR-009 capacity) for the
    // upload OR the job submission — sometimes even just after /api/health went
    // warm. On a cold-start error we drop back into the self-updating "starting up"
    // state, poll /api/health, and retry — but we retry the two steps SEPARATELY so
    // we never re-run a step that already succeeded:
    //   • Upload the bytes EXACTLY ONCE on success. A cold-start failure BEFORE the
    //     upload succeeds stored nothing, so re-warming and retrying the upload is
    //     safe (not a duplicate). Once the upload succeeds we never re-upload.
    //   • Retry ONLY the submitJob call on a cold-start 502/503 — never the upload.
    //     Backend idempotency (keyed on upload_id + period) returns the SAME job, so
    //     a retried submit can never spawn a duplicate job.
    // This is the visible retry — the user never lands on a dead-end "warming up"
    // message and never has to click again.
    const isCold = (err: unknown) =>
      [502, 503].includes((err as { response?: { status?: number } })?.response?.status ?? 0)
    const waitUntilWarm = async (): Promise<boolean> => {
      setUploadPhase('warming')
      for (;;) {
        let warm = false
        try { warm = await api.getHealth() } catch { warm = false }
        if (warm) return true
        if (Date.now() - startedAt > MAX_MS) return false
        await new Promise((r) => setTimeout(r, 6_000))
        setWarmWaited(Math.round((Date.now() - startedAt) / 1000))
      }
    }

    try {
      // Proactive warm so the first write rarely hits a cold endpoint at all.
      let warm = false
      try { warm = await api.getHealth() } catch { warm = false }
      if (!warm && !(await waitUntilWarm())) {
        setError('The analysis service is still starting up after being idle. Please try again in a minute.')
        return
      }

      // 1) Upload the bytes — retried ONLY if the upload itself fails cold (nothing
      //    was stored yet). On success this runs exactly once; we never re-upload.
      let uploadId: string
      let detectedPeriod: string
      for (;;) {
        try {
          setUploadPct(0)
          setUploadPhase('sending')
          // period is the client-side fallback — the backend still auto-detects
          // per document and returns the resolved period; use that downstream.
          const res = await api.upload(
            files, period || undefined,
            // Once the bytes are all sent, the request is waiting on the server —
            // flip to 'processing' so the UI stops implying it's stuck.
            (pct) => { setUploadPct(pct); if (pct >= 100) setUploadPhase('processing') },
            fileNames,
          )
          uploadId = res.uploadId
          detectedPeriod = res.period
          break
        } catch (err: unknown) {
          if (isCold(err) && Date.now() - startedAt < MAX_MS) {
            // Cold-start before the upload landed → warm again, then retry upload.
            if (await waitUntilWarm()) continue
            setError('The analysis service is still starting up after being idle. Please try again in a minute.')
            return
          }
          setError(err instanceof Error ? err.message : 'Upload failed')
          return
        }
      }
      setUploadPhase('processing')
      setPeriod(detectedPeriod)

      // 2) Start the extraction run — retried ONLY here on a cold-start 502/503.
      //    We NEVER re-upload the bytes. Backend idempotency (upload_id + period)
      //    guarantees the SAME job id is returned, so a retried submit can never
      //    spawn a duplicate job.
      for (;;) {
        try {
          const job = await api.submitJob(uploadId, detectedPeriod)
          setJobId(job.id)
          setStep(1)
          return
        } catch (err: unknown) {
          if (isCold(err) && Date.now() - startedAt < MAX_MS) {
            // Cold-start on submit → warm again, then retry ONLY the submit.
            if (await waitUntilWarm()) { setUploadPhase('processing'); continue }
            setError('The analysis service is still starting up after being idle. Please try again in a minute.')
            return
          }
          setError(err instanceof Error ? err.message : 'Upload failed')
          return
        }
      }
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
      const rows: ReviewRow[] = docs.map((doc, i) => ({
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

  // Confirm review → persist the approved set → THEN start the analysis run.
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
      // Persist first so the analysis run reads only the reviewed set.
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

  // Analysis complete → hand back to the host (modal) or navigate (standalone).
  const handleAnalysisComplete = () => {
    setStep(4)
    completeTimerRef.current = window.setTimeout(() => {
      if (onComplete) onComplete(period)
      else navigate(`/dashboard/${period}`)
    }, 1500)
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

  const inner = (
    <Space direction="vertical" size={32} style={{ width: '100%' }}>
      {/* Standalone page header — hidden when embedded in the Dashboard modal. */}
      {!onComplete && (
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
      )}

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

            {demo && (
              <Alert
                type="info"
                showIcon
                message="Demo mode — sample run"
                description="Uploading runs a pre-loaded sample document set through the pipeline UI so you can see the full flow. Your own file isn't processed. Sign in to analyse your own documents."
              />
            )}

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
                disabled={submitting}
                showUploadList={{ showRemoveIcon: !submitting }}
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

            {/* Editable fallback-period control — client-side UI over the existing
                optional-period upload API. */}
            {fileList.length > 0 && period && (
              <div style={{
                background: token.colorFillAlter,
                border: `1px solid ${token.colorBorderSecondary}`,
                borderRadius: token.borderRadius,
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
              }}>
                <CalendarOutlined style={{ color: token.colorPrimary }} />
                {editingPeriod ? (
                  <Select
                    size="small"
                    defaultValue={period}
                    options={PERIOD_OPTIONS}
                    onChange={(v: string) => { setPeriod(v); setEditingPeriod(false) }}
                    onBlur={() => setEditingPeriod(false)}
                    style={{ minWidth: 160 }}
                    autoFocus
                    open
                  />
                ) : (
                  <>
                    <Tooltip title="Each document's own date takes priority. This period is used only for documents where no date is detected.">
                      <Text>
                        Fallback period: <strong>{fmtPeriod(period)}</strong>
                      </Text>
                    </Tooltip>
                    <Tooltip title="Change fallback period">
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => setEditingPeriod(true)}
                      />
                    </Tooltip>
                  </>
                )}
              </div>
            )}

            {submitting && (
              <div>
                {uploadPhase === 'warming' ? (
                  <>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <Spin size="small" style={{ marginRight: 8 }} />
                      Starting the analysis service…
                    </Text>
                    <Progress
                      percent={100}
                      size="small"
                      status="active"
                      showInfo={false}
                      style={{ marginTop: 4 }}
                    />
                    <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
                      The serverless endpoint scales to zero when idle, so the first
                      use after a pause takes a moment to start (usually under a
                      minute). Your upload begins automatically the instant it's ready
                      — no need to click again.{warmWaited > 0 ? ` (waited ${warmWaited}s)` : ''}
                    </Text>
                  </>
                ) : uploadPhase === 'sending' ? (
                  <>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Uploading {fileList.length} file{fileList.length !== 1 ? 's' : ''}…
                    </Text>
                    <Progress
                      percent={uploadPct}
                      size="small"
                      status="active"
                      style={{ marginTop: 4 }}
                      format={pct => `${Math.round(((pct ?? 0) / 100) * fileList.length)} / ${fileList.length}`}
                    />
                  </>
                ) : (
                  <>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <Spin size="small" style={{ marginRight: 8 }} />
                      Files received — starting the extraction pipeline…
                    </Text>
                    <Progress
                      percent={100}
                      size="small"
                      status="active"
                      showInfo={false}
                      style={{ marginTop: 4 }}
                    />
                    <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
                      The serverless endpoint may be warming up — first use can take up
                      to a minute. This keeps running on its own; no need to click again.
                    </Text>
                  </>
                )}
              </div>
            )}

            {error && <Alert type="error" message={error} showIcon />}

            <Button
              type="primary"
              size="large"
              icon={<RocketOutlined />}
              block
              loading={submitting}
              disabled={fileList.length === 0 || editingPeriod}
              onClick={handleSubmit}
            >
              {submitting ? 'Uploading…' : 'Extract & Analyse'}
            </Button>
          </Space>
        </Card>
      )}

      {step === 1 && jobId && (
        <JobStatus
          jobId={jobId}
          label="Extraction run"
          runningMessage="Processing documents with vision LLM (Qwen2.5-VL-72B)…"
          onComplete={handleExtractionComplete}
          onDismiss={() => { setJobId(null); setStep(0) }}
        />
      )}

      {/* ── Step 2: document review + entity-ownership guard ─────────── */}
      {step === 2 && (
        <Card title="Review extracted documents" loading={reviewLoading}>
          {!reviewLoading && (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              {demo && (
                <Alert
                  type="info"
                  showIcon
                  message={
                    <Space size={8}>
                      <Tag color="blue">Sample dataset (demo mode)</Tag>
                      <span>These rows are a pre-loaded sample — not your uploaded file.</span>
                    </Space>
                  }
                />
              )}

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
          label="Analysis run"
          runningMessage="Running 7-agent financial analysis pipeline…"
          pollFn={api.getAnalysisJob}
          onComplete={handleAnalysisComplete}
          onDismiss={() => { setAnalysisJobId(null); setStep(2) }}
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
  )

  // Embedded (modal) mode: padded inner content, no outer Layout.
  if (onComplete) {
    return <div style={{ padding: 24 }}>{inner}</div>
  }

  // Standalone page mode.
  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }}>
      <Content style={{ maxWidth: 800, margin: '0 auto', padding: '48px 24px' }}>
        {inner}
      </Content>
    </Layout>
  )
}
