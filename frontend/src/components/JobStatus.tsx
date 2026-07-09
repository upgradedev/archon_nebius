import { useEffect, useRef, useState } from 'react'
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

  const [elapsed, setElapsed] = useState(0)

  // Reset elapsed when job ID changes
  useEffect(() => {
    setElapsed(0)
  }, [jobId])

  // Count seconds while job is active (pending or running)
  useEffect(() => {
    if (!job || job.status === 'completed' || job.status === 'failed') {
      return
    }
    const timer = setInterval(() => {
      setElapsed(prev => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [jobId, job?.status])

  // Fire onComplete exactly once, even though the query keeps a `completed` job
  // cached across re-renders (the effect re-runs whenever onComplete's identity
  // changes). Without the ref an unstable onComplete would re-trigger the parent's
  // completion flow repeatedly.
  const hasCompletedRef = useRef(false)
  useEffect(() => {
    if (job?.status === 'completed' && !hasCompletedRef.current) {
      hasCompletedRef.current = true
      onComplete()
    }
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

  const getTimerTag = () => {
    if (job.status === 'completed' || job.status === 'failed') return null

    let style: React.CSSProperties = {}
    if (elapsed >= 30 && elapsed < 60) {
      style = { backgroundColor: '#fffb8f', color: '#000000', borderColor: '#ffe58f' }
    } else if (elapsed >= 60) {
      style = { backgroundColor: '#ffd591', color: '#000000', borderColor: '#ffc069' }
    } else {
      style = { backgroundColor: '#f5f5f5', color: 'rgba(0,0,0,0.85)', borderColor: '#d9d9d9' }
    }

    return (
      <Tag style={style}>
        Automated Deploy: {elapsed}s
      </Tag>
    )
  }

  return (
    <Card>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space wrap>
          {icon}
          <Text strong>{label}</Text>
          <Tag color={STATUS_COLOR[job.status]}>{job.status.toUpperCase()}</Tag>
          {getTimerTag()}
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

        {/* A failed job always exposes a recovery action so the user is never
            stranded on a red card. onDismiss (supplied by every caller) resets the
            host flow; the best-effort deleteJob clears the failed job server-side. */}
        {job.status === 'failed' && (
          <Button
            size="small"
            onClick={() => {
              api.deleteJob(jobId).catch(() => {/* best-effort — backend sweep handles it next time */})
              onDismiss?.()
            }}
          >
            Dismiss &amp; Retry
          </Button>
        )}
      </Space>
    </Card>
  )
}
