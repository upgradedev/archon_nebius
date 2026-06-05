import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { MonthlyPnL } from '../types/financial'

interface Props {
  data: MonthlyPnL
}

const fmt = (v: number) =>
  new Intl.NumberFormat('en-EU', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

export default function PnLChart({ data }: Props) {
  const chartData = [
    {
      name: data.period,
      Revenue: data.revenue,
      Expenses: -data.expenses,
      'Net Profit': data.netProfit,
    },
  ]

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ top: 8, right: 16, left: 16, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="name" stroke="#888" />
        <YAxis tickFormatter={v => `€${(v / 1000).toFixed(0)}k`} stroke="#888" />
        <Tooltip formatter={(v: number) => fmt(Math.abs(v))} />
        <Legend />
        <ReferenceLine y={0} stroke="#666" />
        <Bar dataKey="Revenue" fill="#6366f1" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Expenses" fill="#f43f5e" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Net Profit" fill="#22c55e" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
