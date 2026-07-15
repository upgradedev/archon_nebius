// Seeded sample report for demo mode (see demoMode.ts). Figures are illustrative
// but internally consistent with the production P&L, cash-flow, and R1-R4 rules:
//   sales invoices sum to EUR 96,400; eligible expenses sum to EUR 71,850
//   purchase/expense docs + the bank-confirmed payroll transfer produce EUR 32,250
//   in the current assumption-based cash-flow view
//   six payslips sum to the EUR 10,700 bank transfer; the payroll register reports
//   EUR 18,400 employer cost, EUR 10,700 net pay, and six employees
// This compares document values; it does not verify separate tax or social-
// insurance remittance transactions.
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
    grossMarginPct: 25.47,
    operatingMarginPct: 25.47,
  },
  cashFlow: {
    period: DEMO_PERIOD,
    operating: 32_250,
    investing: 0,
    financing: 0,
    net: 32_250,
  },
  expenseBreakdown: [
    { category: 'Operating Expenses', amount: 27_950, percentage: 38.9, monthOverMonthPct: 0 },
    { category: 'Payroll', amount: 18_400, percentage: 25.6, monthOverMonthPct: 0 },
    { category: 'Software & Cloud', amount: 15_900, percentage: 22.1, monthOverMonthPct: 0 },
    { category: 'Rent & Facilities', amount: 9_600, percentage: 13.4, monthOverMonthPct: 0 },
  ],
  topVendors: [
    { name: 'Delta Operating Supplies', totalAmount: 13_000, invoiceCount: 1, avgDaysToPay: 30 },
    { name: 'City Center Offices Rent', totalAmount: 9_600, invoiceCount: 1, avgDaysToPay: 30 },
    { name: 'Meridian Advisory Partners', totalAmount: 8_750, invoiceCount: 1, avgDaysToPay: 30 },
  ],
  keyMetrics: {
    revenueGrowthPct: null,
    expenseRatioPct: 74.5,
    cashBurnRate: 2_395,
    invoiceCount: 12,
    avgInvoiceValue: 12_487.5,
    collectionRatePct: null,
  },
  // Payroll comparison: the bank document contains net wages while the register
  // contains total employer cost. This gap is not evidence of tax remittance.
  payrollGap: {
    bankTransferNet: 10_700,
    trueEmployerCost: 18_400,
    gapPct: 72.0,
    employeeCount: 6,
  },
  // Cross-document validation ledger for this period. All four rules have the
  // required fixture fields and pass the same arithmetic as the analysis agent.
  validations: [
    { id: 'R1', check: 'Bank net ≈ Σ payslip nets (±2%)', state: 'pass' },
    { id: 'R2', check: 'Employer-cost ÷ net ratio in band', state: 'pass' },
    { id: 'R3', check: 'Payment date ≤ end of pay period', state: 'pass' },
    { id: 'R4', check: 'Register headcount == payslip count', state: 'pass' },
  ],
  executiveSummary:
    'The January document set reports revenue of EUR 96,400, expenses of EUR 71,850, ' +
    'and net profit of EUR 24,550, a simplified document margin of 25.47%. For payroll, ' +
    'the bank confirmation records EUR 10,700 in net wages, the six payslips total the same ' +
    'amount, and the payroll register reports total employer cost of EUR 18,400. All four ' +
    'available payroll checks passed: net transfer versus payslips, employer-cost ratio, ' +
    'payment date, and headcount. These checks compare uploaded document values; they do not ' +
    'confirm that separate tax or social-insurance remittances were paid. Under the current ' +
    'cash-flow assumptions, the documents produce EUR 32,250 operating and net cash flow; ' +
    'collection rate and period-over-period growth are unavailable from this single-period set.',
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
// the Review step lists synthetic rows. The amounts below reproduce DEMO_REPORT
// under the same arithmetic used by the production agents.
export const DEMO_DOCUMENTS: ExtractedDoc[] = [
  // Sales invoices — sum to €96,400 (the reported revenue).
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3001.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Acme Buyer Ltd', invoice_number: 'INV-3001', issue_date: '2026-01-08', total_amount: 34_200, currency: 'EUR', confidence: 0.98 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3002.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Blue Ridge SA', invoice_number: 'INV-3002', issue_date: '2026-01-15', total_amount: 28_900, currency: 'EUR', confidence: 0.97 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3003.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Corex Ltd', invoice_number: 'INV-3003', issue_date: '2026-01-22', total_amount: 19_800, currency: 'EUR', confidence: 0.96 },
  { source_file: `raw-docs/${DEMO_PERIOD}/sales-invoice-3004.pdf`, doc_type: 'sales', vendor_name: 'Northwind Trading Ltd', vendor_tax_id: '800123456', recipient_name: 'Delphi Co', invoice_number: 'INV-3004', issue_date: '2026-01-28', total_amount: 13_500, currency: 'EUR', confidence: 0.95 },

  // Purchase invoices — the top vendors on the expense breakdown.
  { source_file: `raw-docs/${DEMO_PERIOD}/aws-cloud-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Amazon Web Services Cloud', recipient_name: 'Northwind Trading Ltd', invoice_number: 'AWS-8842', issue_date: '2026-01-05', total_amount: 7_420, currency: 'EUR', confidence: 0.94 },
  { source_file: `raw-docs/${DEMO_PERIOD}/google-cloud-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Google Cloud', recipient_name: 'Northwind Trading Ltd', invoice_number: 'GCP-2231', issue_date: '2026-01-06', total_amount: 4_180, currency: 'EUR', confidence: 0.93 },
  { source_file: `raw-docs/${DEMO_PERIOD}/professional-services-invoice.pdf`, doc_type: 'invoice', vendor_name: 'Meridian Advisory Partners', recipient_name: 'Northwind Trading Ltd', invoice_number: 'MAP-114', issue_date: '2026-01-18', total_amount: 8_750, currency: 'EUR', confidence: 0.90 },
  { source_file: `raw-docs/${DEMO_PERIOD}/software-subscription-invoice.pdf`, doc_type: 'invoice', vendor_name: 'CloudBooks Software', recipient_name: 'Northwind Trading Ltd', invoice_number: 'CBS-2601', issue_date: '2026-01-19', total_amount: 4_300, currency: 'EUR', confidence: 0.92 },

  // Expense receipts.
  { source_file: `raw-docs/${DEMO_PERIOD}/rent-utilities-expense.pdf`, doc_type: 'expense', vendor_name: 'City Center Offices Rent', recipient_name: 'Northwind Trading Ltd', invoice_number: 'RENT-2601', issue_date: '2026-01-01', total_amount: 9_600, currency: 'EUR', confidence: 0.92 },
  { source_file: `raw-docs/${DEMO_PERIOD}/toll-logistics-expense.pdf`, doc_type: 'expense', vendor_name: 'Metro Toll Systems', recipient_name: 'Northwind Trading Ltd', invoice_number: 'TOLL-77', issue_date: '2026-01-12', total_amount: 2_960, currency: 'EUR', confidence: 0.88 },
  { source_file: `raw-docs/${DEMO_PERIOD}/freight-logistics-expense.pdf`, doc_type: 'expense', vendor_name: 'Harbor Logistics', recipient_name: 'Northwind Trading Ltd', invoice_number: 'FREIGHT-91', issue_date: '2026-01-20', total_amount: 3_240, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/operating-supplies-expense.pdf`, doc_type: 'expense', vendor_name: 'Delta Operating Supplies', recipient_name: 'Northwind Trading Ltd', invoice_number: 'OPS-421', issue_date: '2026-01-23', total_amount: 13_000, currency: 'EUR', confidence: 0.89 },

  // Payroll register — register-reported employer cost, net pay, and headcount.
  { source_file: `raw-docs/${DEMO_PERIOD}/payroll-register-jan.pdf`, doc_type: 'payroll_register', vendor_name: 'Northwind Trading Ltd', recipient_name: 'Northwind Trading Ltd', invoice_number: 'PR-2026-01', issue_date: '2026-01-25', total_amount: 18_400, employer_cost_total: 18_400, net_pay_total: 10_700, employee_count: 6, currency: 'EUR', confidence: 0.95 },

  // Individual payslips — per-employee detail behind the register.
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-01.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'A. Georgiou', invoice_number: 'PSL-01', issue_date: '2026-01-25', total_amount: 1_980, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-02.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'M. Ioannou', invoice_number: 'PSL-02', issue_date: '2026-01-25', total_amount: 1_760, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-03.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'K. Andreou', invoice_number: 'PSL-03', issue_date: '2026-01-25', total_amount: 1_800, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-04.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'E. Demetriou', invoice_number: 'PSL-04', issue_date: '2026-01-25', total_amount: 1_740, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-05.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'N. Nicolaou', invoice_number: 'PSL-05', issue_date: '2026-01-25', total_amount: 1_720, currency: 'EUR', confidence: 0.91 },
  { source_file: `raw-docs/${DEMO_PERIOD}/payslip-employee-06.pdf`, doc_type: 'payslip', vendor_name: 'Northwind Trading Ltd', recipient_name: 'P. Christou', invoice_number: 'PSL-06', issue_date: '2026-01-25', total_amount: 1_700, currency: 'EUR', confidence: 0.91 },

  // Bank confirmation — the net cash that actually left the account (€10,700).
  { source_file: `raw-docs/${DEMO_PERIOD}/bank-confirmation-jan.pdf`, doc_type: 'bank_confirmation', vendor_name: 'National Bank', recipient_name: 'Northwind Trading Ltd', invoice_number: 'BANK-0125', issue_date: '2026-01-25', total_amount: 10_700, bank_transfer_amount: 10_700, currency: 'EUR', confidence: 0.96 },
]

// A synthetic completed Job. Demo mode short-circuits every job poll to this so
// the extraction / analysis status cards land on "completed" with no compute.
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
