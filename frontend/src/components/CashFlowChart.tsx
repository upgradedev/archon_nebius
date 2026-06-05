import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { CashFlow } from '../types/financial'

interface Props {
  data: CashFlow
}

const fmt = (v: number) =>
  new Intl.NumberFormat('en-EU', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

export default function CashFlowChart({ data }: Props) {
  const chartData = [
    { name: 'Operating', value: data.operating },
    { name: 'Investing', value: data.investing },
    { name: 'Financing', value: data.financing },
    { name: 'Net', value: data.net },
  ]

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ top: 8, right: 16, left: 16, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="name" stroke="#888" />
        <YAxis tickFormatter={v => `€${(v / 1000).toFixed(0)}k`} stroke="#888" />
        <Tooltip formatter={(v: number) => fmt(v)} />
        <Legend />
        <ReferenceLine y={0} stroke="#666" />
        <Bar
          dataKey="value"
          name="Cash Flow"
          fill="#6366f1"
          radius={[4, 4, 0, 0]}
          label={{ position: 'top', formatter: (v: number) => `€${(v / 1000).toFixed(1)}k`, fill: '#888', fontSize: 11 }}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
