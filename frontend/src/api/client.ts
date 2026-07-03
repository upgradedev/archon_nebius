import axios from 'axios'
import { auth } from '../firebase'
import type {
  UploadResponse, Job, AnalysisResponse, PeriodInfo, CompanyProfile,
  FinancialReport, ValidationRule, ValidationState, ExtractedDoc,
} from '../types/financial'
import { isDemoMode } from '../demo/demoMode'
import { DEMO_PERIODS, DEMO_REPORT, DEMO_PROFILE } from '../demo/demoData'

// ── Report normalisation ──────────────────────────────────────────────────────
// The analysis endpoint (endpoints/analysis) emits `payrollEvents` and
// `validationResults`, but the dashboard renders the derived `payrollGap` and
// `validations` shapes (see PayrollGapCard / ValidationLedger). Without this
// adapter those cards read `undefined` on a real payload and never render — they
// only appeared in demo mode, whose fixture is already hand-shaped to the derived
// form. We map the raw event/result records into the derived shapes here so the
// production dashboard matches the demo. The demo path early-returns before this.

interface RawPayrollEvent {
  net_total?: number | null            // bank transfer when a bank confirmation was fused
  employer_cost_total?: number | null  // gross pay + employer contributions (from the register)
  employee_count?: number | null
}

interface RawValidationResult {
  rule: string       // e.g. "R1: bank.total ≈ sum(payslips) ±2%"
  passed: boolean
  message: string    // "Skipped — …" marks a dormant (skipped) rule
}

type RawReport = FinancialReport & {
  payrollEvents?: RawPayrollEvent[]
  validationResults?: RawValidationResult[]
}

function normalizeReport(resp: AnalysisResponse): AnalysisResponse {
  const report = resp.report as RawReport

  // payrollEvents[0] → payrollGap. Only when the true employer cost and a
  // positive net figure are both present, else the gap % would be NaN/∞.
  if (!report.payrollGap && report.payrollEvents?.length) {
    const ev = report.payrollEvents[0]
    if (
      ev.employer_cost_total != null &&
      ev.net_total != null &&
      ev.net_total > 0
    ) {
      report.payrollGap = {
        bankTransferNet: ev.net_total,
        trueEmployerCost: ev.employer_cost_total,
        gapPct: (ev.employer_cost_total / ev.net_total - 1) * 100,
        employeeCount: ev.employee_count ?? 0,
      }
    }
  }

  // validationResults → validations. A rule is `skip` (dormant) when its message
  // is prefixed "Skipped"; otherwise pass/fail follows the boolean. The rule id
  // (R1…R4) is the token before the colon; the remainder is the description.
  if (!report.validations && report.validationResults?.length) {
    report.validations = report.validationResults.map((r): ValidationRule => {
      const [id, ...rest] = r.rule.split(':')
      const state: ValidationState = r.message?.startsWith('Skipped')
        ? 'skip'
        : r.passed
          ? 'pass'
          : 'fail'
      return {
        id: id.trim(),
        check: rest.join(':').trim() || r.rule,
        state,
      }
    })
  }

  return resp
}

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
  upload: async (
    files: File[],
    period?: string,
    onProgress?: (pct: number) => void,
    fileNames?: string[],
  ): Promise<UploadResponse> => {
    const form = new FormData()
    // Pass explicit filename as third arg to override any OS temp-file name
    files.forEach((f, i) => form.append('files', f, fileNames?.[i] ?? f.name))
    if (period) form.append('period', period)  // optional — backend auto-detects from filenames
    const { data } = await http.post<UploadResponse>('/api/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total))
      },
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

  // Read completed report from Object Storage. In demo mode (see demoMode.ts)
  // this returns the seeded fixture with NO network call — the tour/CI runner
  // renders the real dashboard components without a backend or auth.
  getReport: async (period: string): Promise<AnalysisResponse> => {
    if (isDemoMode()) return DEMO_REPORT
    const { data } = await http.get<AnalysisResponse>(`/api/reports/${period}`)
    return normalizeReport(data)
  },

  getPeriods: async (): Promise<PeriodInfo[]> => {
    if (isDemoMode()) return DEMO_PERIODS
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
    if (isDemoMode()) return DEMO_PROFILE
    const { data } = await http.get<CompanyProfile>('/api/company-profile')
    return data
  },

  updateCompanyProfile: async (profile: CompanyProfile): Promise<CompanyProfile> => {
    const { data } = await http.put<CompanyProfile>('/api/company-profile', profile)
    return data
  },

  // Persist the user-reviewed document set for a period before analysis is
  // submitted. The backend writes these to extracted/{period}/reviewed/documents.json
  // and removes the prior per-upload documents so the analysis job uses only the
  // approved set.
  updateDocuments: async (
    period: string,
    documents: ExtractedDoc[],
  ): Promise<{ period: string; documents: number; deleted: number }> => {
    const { data } = await http.put(`/api/documents/${period}`, { documents })
    return data
  },
}
