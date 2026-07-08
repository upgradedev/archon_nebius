// Seeded sample report for demo mode (see demoMode.ts). Figures are illustrative
// but internally consistent and aligned with the demo narration / slides:
//   bank transfer (net) ~EUR 10,700 · true employer cost ~EUR 18,400
//   → +72% understatement over the bank figure (the employer's own social-security
//     contribution is ~35% of it; employee withholdings the rest)
//   R1–R4 all pass — R2/R4 now ACTIVE (the register's employer-cost / headcount
//     fields are extracted; this was the harness's keystone finding, now fixed)
// No real customer data — synthetic SMB figures for a single month.
import type {
  AnalysisResponse,
  CompanyProfile,
  FinancialReport,
  PeriodInfo,
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
  // The core insight: the bank transfer understates true payroll cost.
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
    'operating margin, up 6.8% on the prior month. The month\'s defining correction is payroll: ' +
    'the bank moved EUR 10,700 in net transfers, but Archon\'s Event Linker fused the bank ' +
    'confirmation, payroll register, and payslips into a single event and recovered the true ' +
    'employer cost of EUR 18,400 — about a 72% understatement that a bank-only close would have ' +
    'booked as the whole payroll line; about half of that gap is the employer\'s own ' +
    'social-security contribution (~35% over the transfer), the rest employee withholdings. ' +
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
