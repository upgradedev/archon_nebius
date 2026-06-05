import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Progress, Space, Typography, Alert, Tag } from 'antd'
import { LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { api } from '../api/client'

const { Text } = Typography

interface Props {
  jobId: string
  onComplete: () => void
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
}

export default function JobStatus({ jobId, onComplete }: Props) {
  const { data: job, error } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.getJob(jobId),
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

  const icon =
    job.status === 'completed' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
    job.status === 'failed'    ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> :
    <LoadingOutlined spin />

  return (
    <Card>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space>
          {icon}
          <Text strong>Extraction job</Text>
          <Tag color={STATUS_COLOR[job.status]}>{job.status.toUpperCase()}</Tag>
        </Space>

        <Progress
          percent={job.progress ?? (job.status === 'completed' ? 100 : job.status === 'running' ? 60 : 10)}
          status={job.status === 'failed' ? 'exception' : job.status === 'completed' ? 'success' : 'active'}
        />

        <Text type="secondary">
          {job.status === 'pending'   && 'Waiting for GPU instance…'}
          {job.status === 'running'   && `Processing ${job.documentsCount} documents with vision LLM…`}
          {job.status === 'completed' && 'All documents extracted. Loading analysis…'}
          {job.status === 'failed'    && (job.errorMessage ?? 'Job failed')}
        </Text>
      </Space>
    </Card>
  )
}
