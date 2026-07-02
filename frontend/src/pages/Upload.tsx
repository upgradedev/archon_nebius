import { useState } from 'react'
import {
  Layout, Typography, Upload as AntUpload, Button,
  Steps, Card, Space, Alert, Tag, theme, Row, Col, Avatar, Tooltip,
} from 'antd'
import { InboxOutlined, RocketOutlined, CheckCircleOutlined, LogoutOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import JobStatus from '../components/JobStatus'
import { useAuth } from '../contexts/AuthContext'

const { Content } = Layout
const { Title, Text } = Typography
const { Dragger } = AntUpload
const { useToken } = theme

const ACCEPTED_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.tif,.webp'

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

  // Extraction complete → submit analysis job
  const handleExtractionComplete = async () => {
    try {
      const analysisJob = await api.analyze(period)
      setAnalysisJobId(analysisJob.id)
      setStep(2)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to submit analysis job')
      setStep(0)
    }
  }

  // Analysis complete → navigate to dashboard
  const handleAnalysisComplete = () => {
    setStep(3)
    setTimeout(() => navigate(`/dashboard/${period}`), 1500)
  }

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
              { title: 'Analyse' },
              { title: 'Ready', icon: step === 3 ? <CheckCircleOutlined /> : undefined },
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

          {step === 2 && analysisJobId && (
            <JobStatus
              jobId={analysisJobId}
              label="Analysis job"
              runningMessage="Running 7-agent financial analysis pipeline…"
              pollFn={api.getAnalysisJob}
              onComplete={handleAnalysisComplete}
            />
          )}

          {step === 3 && (
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
