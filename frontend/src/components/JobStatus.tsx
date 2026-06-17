import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Progress, Space, Typography, Alert, Tag, Button } from 'antd'
import { LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import type { Job } from '../types/financial'

const { Text } = Typography

interface Props {
  jobId: string
  label?: string
  runningMessage?: string
  pollFn?: (jobId: string) => Promise<Job>
  onComplete: () => void
  onDismiss?: () => void
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
}

export default function JobStatus({
  jobId,
  label = 'Extraction job',
  runningMessage,
  pollFn = api.getJob,
  onComplete,
  onDismiss,
}: Props) {
  const { data: job, error } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => pollFn(jobId),
    refetchInterval: query => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 3000
    },
  })

  useEffect(() => {
    if (job?.status === 'completed') onComplete()
  }, [job?.status, onComplete])

  if (error) {
    return <Alert type="error" message="Failed to fetch job status" showIcon />
  }

  if (!job) return null

  const defaultRunningMsg = runningMessage ?? `Processing ${job.documentsCount} documents…`

  const icon =
    job.status === 'completed' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
    job.status === 'failed'    ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> :
    <LoadingOutlined spin />

  return (
    <Card>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space>
          {icon}
          <Text strong>{label}</Text>
          <Tag color={STATUS_COLOR[job.status]}>{job.status.toUpperCase()}</Tag>
        </Space>

        <Progress
          percent={job.progress ?? (job.status === 'completed' ? 100 : job.status === 'running' ? 60 : 10)}
          status={job.status === 'failed' ? 'exception' : job.status === 'completed' ? 'success' : 'active'}
        />

        <Text type="secondary">
          {job.status === 'pending'   && 'Waiting for compute instance…'}
          {job.status === 'running'   && defaultRunningMsg}
          {job.status === 'completed' && 'Done.'}
          {job.status === 'failed'    && (job.errorMessage ?? 'Job failed')}
        </Text>

        {job.status === 'failed' && onDismiss && (
          <Button
            size="small"
            onClick={() => {
              api.deleteJob(jobId).catch(() => {/* best-effort — backend sweep handles it next time */})
              onDismiss()
            }}
          >
            Dismiss &amp; Retry
          </Button>
        )}
      </Space>
    </Card>
  )
}
