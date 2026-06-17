import { Button, Card, Typography } from 'antd'
import { GoogleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const { Title, Text } = Typography

export default function Login() {
  const { signInWithGoogle, user } = useAuth()
  const navigate = useNavigate()

  if (user) {
    navigate('/upload', { replace: true })
    return null
  }

  const handleSignIn = async () => {
    await signInWithGoogle()
    navigate('/upload', { replace: true })
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0a0f',
      }}
    >
      <Card
        style={{
          width: 400,
          textAlign: 'center',
          background: '#141420',
          border: '1px solid #2a2a3d',
          borderRadius: 16,
          padding: '16px 0',
        }}
      >
        <div style={{ marginBottom: 24 }}>
          <span style={{ fontSize: 48 }}>Αρχων</span>
        </div>
        <Title level={3} style={{ color: '#e2e8f0', marginBottom: 4 }}>
          Archon
        </Title>
        <Text style={{ color: '#94a3b8', display: 'block', marginBottom: 32 }}>
          P&L Intelligence for SMBs
        </Text>
        <Button
          icon={<GoogleOutlined />}
          size="large"
          onClick={handleSignIn}
          style={{
            width: '100%',
            background: '#6366f1',
            color: '#fff',
            border: 'none',
            height: 48,
            fontSize: 15,
            fontWeight: 500,
          }}
        >
          Continue with Google
        </Button>
      </Card>
    </div>
  )
}
