import axios from 'axios'
import { auth } from '../firebase'
import type { UploadResponse, Job, AnalysisResponse, PeriodInfo, CompanyProfile } from '../types/financial'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120_000,
})

http.interceptors.request.use(async (config) => {
  const user = auth.currentUser
  if (user) {
    const token = await user.getIdToken()
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const api = {
  upload: async (files: File[], period: string): Promise<UploadResponse> => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    form.append('period', period)
    const { data } = await http.post<UploadResponse>('/api/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  submitJob: async (uploadId: string, period: string): Promise<Job> => {
    const { data } = await http.post<Job>('/api/jobs', { uploadId, period })
    return data
  },

  getJob: async (jobId: string): Promise<Job> => {
    const { data } = await http.get<Job>(`/api/jobs/${jobId}`)
    return data
  },

  // Submit an on-demand analysis job; returns a Job for polling
  analyze: async (period: string): Promise<Job> => {
    const { data } = await http.post<Job>('/api/analyze', { period })
    return data
  },

  // Poll analysis job status
  getAnalysisJob: async (jobId: string): Promise<Job> => {
    const { data } = await http.get<Job>(`/api/analyze/${jobId}`)
    return data
  },

  // Read completed report from Object Storage
  getReport: async (period: string): Promise<AnalysisResponse> => {
    const { data } = await http.get<AnalysisResponse>(`/api/reports/${period}`)
    return data
  },

  getPeriods: async (): Promise<PeriodInfo[]> => {
    const { data } = await http.get<PeriodInfo[]>('/api/periods')
    return data
  },

  deletePeriod: async (period: string): Promise<void> => {
    await http.delete(`/api/periods/${period}`)
  },

  deleteJob: async (jobId: string): Promise<void> => {
    await http.delete(`/api/jobs/${jobId}`)
  },

  getDocuments: async (period: string): Promise<unknown[]> => {
    const { data } = await http.get<unknown[]>(`/api/documents/${period}`)
    return data
  },

  getCompanyProfile: async (): Promise<CompanyProfile> => {
    const { data } = await http.get<CompanyProfile>('/api/company-profile')
    return data
  },

  updateCompanyProfile: async (profile: CompanyProfile): Promise<CompanyProfile> => {
    const { data } = await http.put<CompanyProfile>('/api/company-profile', profile)
    return data
  },
}
