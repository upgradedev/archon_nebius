// Seeded sample report for demo mode (see demoMode.ts). Figures are illustrative
// but internally consistent and aligned with the demo narration / slides:
//   bank transfer (net) ~EUR 10,700 · true employer cost ~EUR 18,400
//   → the bank net is only the net-wages component; adding withheld payroll taxes
//     + the employer's own contributions (~35% over the transfer) reconciles to the
//     register's true cost, ~72% more, every euro tied to a source document
//   R1–R4 all pass — R2/R4 now ACTIVE (the register's employer-cost / headcount
//     fields are extracted; this was the harness's keystone finding, now fixed)
// No real customer data — synthetic SMB figures for a single month.
import type {
  AnalysisResponse,
  CompanyProfile,
  ExtractedDoc,
  FinancialReport,
  Job,
  PeriodInfo,
  UploadResponse,
} from '../types/financial'
import { DEMO_PERIOD } from './demoMode'

const report: FinancialReport = {
  period: DEMO_PERIOD,
  pnl: {
    period: DEMO_PERIOD,
    revenue: 96_400,
    expenses: 71_850,
    netProfit: 24_550,
    grossMarginPct: 38.2,
    operatingMarginPct: 25.5,
  },
  cashFlow: {
    period: DEMO_PERIOD,
    operating: 21_300,
    investing: -6_400,
    financing: -3_000,
    net: 11_900,
  },
  expenseBreakdown: [
    { category: 'Payroll (true employer cost)', amount: 18_400, percentage: 25.6, monthOverMonthPct: 3.1 },
    { category: 'Cloud & software', amount: 15_900, percentage: 22.1, monthOverMonthPct: 8.4 },
    { category: 'Rent & utilities', amount: 9_600, percentage: 13.4, monthOverMonthPct: 0.0 },
    { category: 'Professional services', amount: 8_750, percentage: 12.2, monthOverMonthPct: -4.2 },
    { category: 'Tolls & logistics', amount: 6_200, percentage: 8.6, monthOverMonthPct: 1.7 },
    { category: 'Other operating', amount: 13_000, percentage: 18.1, monthOverMonthPct: 2.0 },
  ],
  topVendors: [
    { name: 'Amazon Web Services', totalAmount: 7_420, invoiceCount: 1, avgDaysToPay: 14 },
    { name: 'Google Cloud', totalAmount: 4_180, invoiceCount: 1, avgDaysToPay: 21 },
    { name: 'Metro Toll Systems', totalAmount: 2_960, invoiceCount: 3, avgDaysToPay: 7 },
  ],
  keyMetrics: {
    revenueGrowthPct: 6.8,
    expenseRatioPct: 74.5,
    cashBurnRate: 0,
    invoiceCount: 27,
    avgInvoiceValue: 3_570,
    collectionRatePct: 92.4,
  },
  // Payroll reconciliation: the bank net is the net-wages component; withheld
  // taxes + employer contributions reconcile up to the register's true cost.
  payrollGap: {
    bankTransferNet: 10_700,
    trueEmployerCost: 18_400,
    gapPct: 72.0,
    employeeCount: 6,
  },
  // Cross-document validation ledger for this period. All four rules fire and
  // pass — R2/R4 now read the register's employer-cost / headcount fields the
  // extractor populates (they were the harness's keystone dormancy finding, now
  // fixed). R2/R4 still legitimately SKIP when a register is absent — not here.
  validations: [
    { id: 'R1', check: 'Bank net ≈ Σ payslip nets (±2%)', state: 'pass' },
    { id: 'R2', check: 'Employer-cost ÷ net ratio in band', state: 'pass' },
    { id: 'R3', check: 'Payment date ≤ end of pay period', state: 'pass' },
    { id: 'R4', check: 'Register headcount == payslip count', state: 'pass' },
  ],
  executiveSummary:
    'January closed with revenue of EUR 96,400 and a net profit of EUR 24,550 — a 25.5% ' +
    'operating margin, up 6.8% on the prior month. The month\'s defining reconciliation is payroll: ' +
    'the bank moved EUR 10,700 in net wages, and Archon\'s Event Linker fused the bank ' +
    'confirmation, payroll register, and payslips into a single event to confirm the register\'s ' +
    'true employer cost of EUR 18,400 — about 72% more, once the withheld payroll taxes and the ' +
    'employer\'s own social-security contributions (~35% over the transfer) are reconciled back to ' +
    'source documents, so every component the register says is owed is accounted for. ' +
    'All four cross-document rules passed: R1 (bank net vs payslip sum) and ' +
    'R3 (payment date), plus R2 (employer-cost ratio) and R4 (headcount), which read register ' +
    'fields the extractor now populates. Cash generation stayed healthy at EUR 11,900 net, with ' +
    'a 92.4% collection rate.',
  generatedAt: `${DEMO_PERIOD}-31T09:12:00Z`,
}

export const DEMO_REPORT: AnalysisResponse = {
  jobId: 'demo-job',
  report,
  generatedAt: report.generatedAt,
}

export const DEMO_PERIODS: PeriodInfo[] = [
  { period: DEMO_PERIOD, hasReport: true, hasExtraction: true },
]

export const DEMO_PROFILE: CompanyProfile = {
  company_name: 'Northwind Trading Ltd',
  company_tax_id: '800123456',
}

// ── Extracted document set backing the demo dashboard ─────────────────────────
// The KPI-tile drill-down (MetricsCards) and the Upload → Review step read the
// period's extracted documents. In demo mode the api client serves THIS synthetic
// set with no network call, so every drillable tile opens a populated table and
// the Review step lists real rows. Figures tie to DEMO_REPORT: sales sum ≈ the
// €96,400 revenue; the payroll register carries the €18,400 true employer cost /
// 6 employees; the bank confirmation carries the €10,700 net transfer — the same
// 3-document fusion the payroll-gap card visualises. Clearly synthetic SMB data.
export const DEMO_DOCUMENTS: ExtractedDoc[] = [
  // Sales invoices — sum to €96,400 (the reported revenue).
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3001.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Acme Buyer Ltd', invoice_number: 'INV-3001', issue_date: '2026-01-08', total_amount: 34_200, currency: 'EUR', confidence: 0.98 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3002.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Blue Ridge SA', invoice_number: 'INV-3002', issue_date: '2026-01-15', total_amount: 28_900, currency: 'EUR', confidence: 0.97 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3003.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Corex Ltd', invoice_number: 'INV-3003', issue_date: '2026-01-22', total_amount: 19_800, currency: 'EUR', confidence: 0.96 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3004.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Delphi Co', invoice_number: 'INV-3004', issue_date: '2026-01-28', total_amount: 13_500, currency: 'EUR', confidence: 0.95 },

  // Purchase invoices — the top vendors on the expense breakdown.
  { source_file: `raw-docs/${DEMO_PERIOD}/aws-cloud-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Amazon Web Services', recipient_name: 'Northwind Trading Ltd', invoice_number: 'AWS-8842', issue_date: '2026-01-05', total_amount: 7_420, currency: 'EUR', confidence: 0.94 },
  { source_file: `raw-docs/${DEMO_PERIOD}/google-cloud-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Google Cloud', recipient_name: 'Northwind Trading Ltd', invoice_number: 'GCP-2231', issue_date: '2026-01-06', total_amount: 4_180, currency: 'EUR', confidence: 0.93 },
  { source_file: `raw-docs/${DEMO_PERIOD}/professional-services-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Meridian Advisory Partners', recipient_name: 'Northwind Trading Ltd', invoice_number: 'MAP-114', issue_date: '2026-01-18', total_amount: 8_750, currency: 'EUR', confidence: 0.90 },

  // Expense receipts.
  { source_file: `raw-docs/${DEMO_PERIOD}/rent-utilities-expense.pdf`, doc_type: 'expense', vendor_name: 'City Center Offices', recipient_name: 'Northwind Trading Ltd', invoice_number: 'RENT-2601', issue_date: '2026-01-01', total_amount: 9_600, currency: 'EUR', confidence: 0.92 },
  { source_file: `raw-docs/${DEMO_PERIOD}/toll-logistics-expense.pdf`, doc_type: 'expense', vendor_name: 'Metro Toll Systems', recipient_name: 'Northwind Trading Ltd', invoice_number: 'TOLL-77', issue_date: '2026-01-12', total_amount: 2_960, currency: 'EUR', confidence: 0.88 },

  // Payroll register — the true employer cost + headcount the Event Linker fuses.
  { source_file: `raw-docs/${DEMO_PERIOD}/payroll-register-jan.pdf`, doc_type: 'payroll_register', vendor_name: 'Northwind Trading Ltd', invoice_number: 'PR-2026-01', issue_date: '2026-01-25', total_amount: 18_400, employer_cost_total: 18_400, employee_count: 6, currency: 'EUR', confidence: 0.95 },

  // Individual payslips — per-employee detail behind the register.
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-01.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'A. Georgiou', invoice_number: 'PSL-01', issue_date: '2026-01-25', total_amount: 1_980, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-02.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'M. Ioannou', invoice_number: 'PSL-02', issue_date: '2026-01-25', total_amount: 1_760, currency: 'EUR', confidence: 0.91 },

  // Bank confirmation — the net cash that actually left the account (€10,700).
  { source_file: `raw-docs/${DEMO_PERIOD}/bank-confirmation-jan.pdf`, doc_type: 'bank_confirmation', vendor_name: 'National Bank', recipient_name: 'Northwind Trading Ltd', invoice_number: 'BANK-0125', issue_date: '2026-01-25', total_amount: 10_700, bank_transfer_amount: 10_700, currency: 'EUR', confidence: 0.96 },
]

// A synthetic completed Job. Demo mode short-circuits every job poll to this so
// the extraction / analysis JobStatus cards land on "completed" with no compute.
export function demoJob(
  jobId: string,
  period: string,
  status: Job['status'] = 'completed',
): Job {
  const now = new Date().toISOString()
  return {
    id: jobId,
    status,
    period,
    documentsCount: DEMO_DOCUMENTS.length,
    createdAt: now,
    completedAt: status === 'completed' ? now : undefined,
    progress: status === 'completed' ? 100 : status === 'running' ? 60 : 10,
  }
}

// A synthetic upload response mirroring what the backend returns for the files a
// judge "uploads" in demo mode. The resolved period is always the seeded period
// so the flow lands on DEMO_REPORT.
export function demoUpload(fileNames: string[]): UploadResponse {
  const now = new Date().toISOString()
  return {
    uploadId: 'demo-upload',
    period: DEMO_PERIOD,
    files: (fileNames.length ? fileNames : ['demo-document.pdf']).map((name, i) => ({
      id: `demo-file-${i}`,
      filename: name,
      sizeBytes: 1024,
      uploadedAt: now,
    })),
  }
}
