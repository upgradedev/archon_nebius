export type DocType = 'invoice' | 'payroll' | 'expense' | 'sales' | 'unknown'

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface UploadedFile {
  id: string
  filename: string
  sizeBytes: number
  uploadedAt: string
}

export interface UploadResponse {
  uploadId: string
  files: UploadedFile[]
}

export interface Job {
  id: string
  status: JobStatus
  period: string        // YYYY-MM
  documentsCount: number
  createdAt: string
  completedAt?: string
  errorMessage?: string
  progress?: number     // 0-100
}

export interface MonthlyPnL {
  period: string        // YYYY-MM
  revenue: number
  expenses: number
  netProfit: number
  grossMarginPct: number
  operatingMarginPct: number
}

export interface CashFlow {
  period: string
  operating: number
  investing: number
  financing: number
  net: number
}

export interface ExpenseCategory {
  category: string
  amount: number
  percentage: number
  monthOverMonthPct: number
}

export interface VendorSummary {
  name: string
  totalAmount: number
  invoiceCount: number
  avgDaysToPay: number
}

export interface KeyMetrics {
  revenueGrowthPct: number
  expenseRatioPct: number
  cashBurnRate: number
  invoiceCount: number
  avgInvoiceValue: number
  collectionRatePct: number
}

export interface FinancialReport {
  period: string
  pnl: MonthlyPnL
  cashFlow: CashFlow
  expenseBreakdown: ExpenseCategory[]
  topVendors: VendorSummary[]
  keyMetrics: KeyMetrics
  executiveSummary: string
  generatedAt: string
}

export interface AnalysisResponse {
  jobId: string
  report: FinancialReport
}
