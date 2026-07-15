import { useState, useCallback, useEffect } from 'react'
import { Button, Input, Divider, message } from 'antd'
import { GoogleOutlined, MailOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import './Login.css'

/* Subtle P&L chart lines drawn as decorative SVG background */
function ChartBackground() {
  return (
    <svg className="chart-bg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden>
      {/* Grid lines */}
      {[180, 360, 540, 720].map(y => (
        <line key={y} x1="0" y1={y} x2="1440" y2={y}
          stroke="rgba(99,102,241,0.05)" strokeWidth="1" />
      ))}
      {[240, 480, 720, 960, 1200].map(x => (
        <line key={x} x1={x} y1="0" x2={x} y2="900"
          stroke="rgba(99,102,241,0.04)" strokeWidth="1" />
      ))}

      {/* Primary P&L trend line — indigo, animated draw */}
      <polyline
        className="chart-line"
        points="0,680 120,640 240,660 360,540 480,570 600,440 720,470 840,350 960,370 1080,270 1200,240 1320,190 1440,160"
        stroke="rgba(99,102,241,0.28)" strokeWidth="2.5"
      />

      {/* Secondary line — violet, slower draw */}
      <polyline
        className="chart-line"
        points="0,780 160,750 320,720 480,700 640,670 800,630 960,590 1120,560 1280,530 1440,510"
        stroke="rgba(139,92,246,0.15)" strokeWidth="1.5"
        style={{ animationDelay: '.4s', animationDuration: '3s' }}
      />

      {/* Area fill under primary line */}
      <polyline
        points="0,680 120,640 240,660 360,540 480,570 600,440 720,470 840,350 960,370 1080,270 1200,240 1320,190 1440,160 1440,900 0,900"
        fill="url(#areaGradient)"
        style={{ opacity: 0.12 }}
      />

      {/* Bar silhouettes at the bottom */}
      {[
        { x: 80,  h: 90 },
        { x: 160, h: 130 },
        { x: 240, h: 100 },
        { x: 320, h: 170 },
        { x: 400, h: 145 },
        { x: 480, h: 195 },
        { x: 560, h: 160 },
        { x: 640, h: 220 },
      ].map(({ x, h }) => (
        <rect key={x} x={x} y={900 - h} width={38} height={h}
          fill="rgba(99,102,241,0.09)" rx="3" />
      ))}

      <defs>
        <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#6366f1" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
    </svg>
  )
}

export default function Login() {
  const { signInWithGoogle, signInWithEmail, user } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [emailLoading, setEmailLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [cardOffset, setCardOffset] = useState({ x: 0, y: 0 })

  /* Redirect if already signed in. Navigation is a side effect — never call it
     during render — so it runs in an effect; the component renders nothing while
     the redirect is in flight. */
  useEffect(() => {
    if (user) navigate('/', { replace: true })
  }, [user, navigate])

  if (user) return null

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const x = (e.clientX / window.innerWidth  - 0.5) * 14
    const y = (e.clientY / window.innerHeight - 0.5) * 10
    setCardOffset({ x, y })
  }, [])

  const handleMouseLeave = () => setCardOffset({ x: 0, y: 0 })

  const handleSignIn = async () => {
    setLoading(true)
    try {
      await signInWithGoogle()
      navigate('/', { replace: true })
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'Sign-in failed')
      setLoading(false)
    }
  }

  const handleEmailSignIn = async () => {
    if (!email || !password) {
      message.warning('Enter your email and password')
      return
    }
    setEmailLoading(true)
    try {
      await signInWithEmail(email.trim(), password)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'Sign-in failed')
      setEmailLoading(false)
    }
  }

  return (
    <div
      className="login-root"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Ambient glow orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />

      {/* Decorative chart lines */}
      <ChartBackground />

      {/* Glass card — shifts with cursor for parallax depth */}
      <div
        className="login-card"
        style={{
          transform: `translate(${cardOffset.x}px, ${cardOffset.y}px)`,
        }}
      >
        <div className="brand-greek">Αρχων</div>
        <div className="brand-label">Archon</div>

        <div className="brand-divider" />

        <p className="tagline">
          Financial document control for SMBs.<br />
          Extract, classify, review, and exclude records,<br />
          then run deterministic period and payroll checks.
        </p>

        <Button
          className="google-btn"
          icon={<GoogleOutlined />}
          size="large"
          loading={loading}
          onClick={handleSignIn}
        >
          Continue with Google
        </Button>

        <Divider plain style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>or</Divider>

        <form
          className="email-form"
          onSubmit={(e) => { e.preventDefault(); void handleEmailSignIn() }}
        >
          <Input
            size="large"
            type="email"
            autoComplete="email"
            aria-label="Email"
            prefix={<MailOutlined />}
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ marginBottom: 10 }}
          />
          <Input.Password
            size="large"
            autoComplete="current-password"
            aria-label="Password"
            prefix={<LockOutlined />}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ marginBottom: 12 }}
          />
          <Button
            className="email-btn"
            type="primary"
            size="large"
            block
            htmlType="submit"
            loading={emailLoading}
          >
            Sign in with email
          </Button>
        </form>

        <p className="login-footer">
          Your documents are processed on Nebius Serverless AI.<br />
          No data is stored beyond your session.
        </p>
      </div>
    </div>
  )
}
