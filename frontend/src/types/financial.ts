export type DocType =
  | 'invoice'
  | 'sales'
  | 'expense'
  | 'payroll_register'
  | 'bank_confirmation'
  | 'payslip'
  | 'payroll'
  | 'account_statement'
  | 'unknown'

// Options for the per-row document-type selector in the Review step. Labels are
// universal (no jurisdiction-specific terminology).
export const DOC_TYPE_OPTIONS: { value: DocType; label: string }[] = [
  { value: 'sales',             label: 'Sales Invoice' },
  { value: 'invoice',           label: 'Purchase Invoice' },
  { value: 'expense',           label: 'Expense' },
  { value: 'payroll_register',  label: 'Payroll Register' },
  { value: 'payslip',           label: 'Payslip' },
  { value: 'payroll',           label: 'Payroll' },
  { value: 'bank_confirmation', label: 'Bank Statement' },
  { value: 'account_statement', label: 'Account Statement' },
  { value: 'unknown',           label: 'Unknown' },
]

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface UploadedFile {
  id: string
  filename: string
  sizeBytes: number
  uploadedAt: string
}

export interface UploadResponse {
  uploadId: string
  period: string
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

// Payroll-gap insight — the core "hidden cost" story. The bank transfer (net)
// understates the true employer cost; the wedge is the employer social-security
// contribution. Optional: present only when the report fused a payroll event.
export interface PayrollGap {
  bankTransferNet: number      // what actually left the account
  trueEmployerCost: number     // gross pay + employer social security
  gapPct: number               // (true / bank − 1) × 100
  employeeCount: number
}

// One cross-document validation rule (R1–R4) as evaluated for this period.
export type ValidationState = 'pass' | 'fail' | 'skip'

export interface ValidationRule {
  id: string                   // R1 … R4
  check: string                // human-readable description
  state: ValidationState       // pass / fail / skip (dormant — field never extracted)
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
  payrollGap?: PayrollGap        // optional — rendered when a payroll event was fused
  validations?: ValidationRule[] // optional — R1–R4 cross-document ledger
}

export interface AnalysisResponse {
  jobId: string
  report: FinancialReport
  generatedAt?: string
}

export interface PeriodInfo {
  period: string
  hasReport: boolean
  hasExtraction: boolean
}

export interface CompanyProfile {
  company_name: string
  company_tax_id: string
}

export interface ExtractedDoc {
  // Nebius extraction serialises the file name as `source_file`; `filename` is
  // kept for backward-compat with older fixtures. Renderers read either.
  filename?: string
  source_file?: string
  doc_type: DocType
  period?: string
  vendor_name?: string
  vendor_tax_id?: string
  recipient_name?: string
  total_amount?: number
  currency?: string
  employer_cost_total?: number
  bank_transfer_amount?: number
  employee_count?: number
  // ── Drill-down columns (appended, all optional) ──────────────────────────────
  // `source_file` and `recipient_name` are already declared above (added by the
  // Upload/extraction slice). The remaining fields back the KPI drill-down
  // document table (see MetricsCards). Kept additive/optional so extractor payloads
  // that omit them still type-check.
  invoice_number?: string
  issue_date?: string
  subtotal?: number
  vat_amount?: number
  confidence?: number
}
