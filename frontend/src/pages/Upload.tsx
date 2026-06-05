import { useState } from 'react'
import {
  Layout, Typography, Upload as AntUpload, Button, DatePicker,
  Steps, Card, Space, Alert, Tag, theme,
} from 'antd'
import { InboxOutlined, RocketOutlined, CheckCircleOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { api } from '../api/client'
import JobStatus from '../components/JobStatus'

const { Content } = Layout
const { Title, Text } = Typography
const { Dragger } = AntUpload
const { useToken } = theme

const ACCEPTED_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.tif,.webp'

export default function UploadPage() {
  const { token } = useToken()
  const navigate = useNavigate()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [period, setPeriod] = useState<string>('')
  const [step, setStep] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!period || fileList.length === 0) return
    setError(null)
    setSubmitting(true)
    try {
      const files = fileList.map(f => f.originFileObj as File)
      const { uploadId } = await api.upload(files, period)
      const job = await api.submitJob(uploadId, period)
      setJobId(job.id)
      setStep(1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleJobComplete = () => {
    setStep(2)
    setTimeout(() => navigate(`/dashboard/${period}`), 1500)
  }

  return (
    <Layout style={{ minHeight: '100vh', background: token.colorBgLayout }}>
      <Content style={{ maxWidth: 800, margin: '0 auto', padding: '48px 24px' }}>
        <Space direction="vertical" size={32} style={{ width: '100%' }}>
          <div>
            <Title level={2} style={{ margin: 0 }}>Archon</Title>
            <Text type="secondary">Agentic Financial Intelligence — upload documents, get P&L insights</Text>
          </div>

          <Steps
            current={step}
            items={[
              { title: 'Upload documents' },
              { title: 'Extracting data' },
              { title: 'Ready', icon: step === 2 ? <CheckCircleOutlined /> : undefined },
            ]}
          />

          {step === 0 && (
            <Card>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div>
                  <Text strong>Reporting period</Text>
                  <br />
                  <DatePicker
                    picker="month"
                    style={{ marginTop: 8, width: '100%' }}
                    onChange={(_, s) => setPeriod(s as string)}
                    disabledDate={d => d.isAfter(dayjs())}
                    placeholder="Select month"
                  />
                </div>

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
                      PDF · DOCX · JPG · PNG · TIFF — scanned or digital, Greek or English
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
                  disabled={!period || fileList.length === 0}
                  onClick={handleSubmit}
                >
                  Extract & Analyze
                </Button>
              </Space>
            </Card>
          )}

          {step === 1 && jobId && (
            <JobStatus jobId={jobId} onComplete={handleJobComplete} />
          )}

          {step === 2 && (
            <Alert
              type="success"
              message="Extraction complete — loading dashboard..."
              showIcon
            />
          )}
        </Space>
      </Content>
    </Layout>
  )
}
