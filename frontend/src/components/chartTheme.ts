// Shared Recharts tooltip theme.
//
// Recharts' default <Tooltip> renders a WHITE content box with dark text and a
// near-white hover "cursor" highlight rectangle. The app runs Ant Design's dark
// algorithm (dark canvas), so the default tooltip flashed as a jarring white
// block with poor contrast on hover. These constants give every chart tooltip an
// explicit dark surface, legible light text and a subtle translucent cursor that
// reads correctly against the dark bars — applied uniformly across PnLChart,
// CashFlowChart and ExpenseBreakdown so the dashboard stays visually consistent.

import type { CSSProperties } from 'react'

// Dark tooltip surface: matches the dashboard's elevated dark cards.
export const tooltipContentStyle: CSSProperties = {
  background: '#1f2937',
  border: '1px solid #374151',
  borderRadius: 8,
  color: '#e5e7eb',
  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.45)',
}

// The header row (category / period label) inside the tooltip.
export const tooltipLabelStyle: CSSProperties = {
  color: '#e5e7eb',
  fontWeight: 600,
  marginBottom: 4,
}

// Each series row (name + value) inside the tooltip.
export const tooltipItemStyle: CSSProperties = {
  color: '#e5e7eb',
}

// The hover highlight behind the bars — a faint brand-tinted wash instead of the
// default near-white fill that looked like "white on white" over dark bars.
export const tooltipCursor = { fill: 'rgba(99, 102, 241, 0.15)' }
