import { useState } from 'react'
import { Alert, Button, Card, Input, Space, Typography } from 'antd'
import { apiRequest } from './api'

const { Text, Title } = Typography

type MfaSetupProps = {
  csrfToken: string
  onComplete: () => void | Promise<void>
}

type MfaSetupResponse = {
  secret: string
}

function MfaSetup({ csrfToken, onComplete }: MfaSetupProps) {
  const [secret, setSecret] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const requestHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }

  const startSetup = async () => {
    setError('')
    setSaving(true)
    try {
      const setup = await apiRequest<MfaSetupResponse>('/auth/mfa/setup', {
        method: 'POST',
        headers: requestHeaders,
      })
      setSecret(setup.secret)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to start MFA setup.')
    } finally {
      setSaving(false)
    }
  }

  const confirmSetup = async () => {
    setError('')
    if (!/^[0-9]{6}$/.test(code)) {
      setError('Enter the current 6-digit code from your authenticator app.')
      return
    }
    setSaving(true)
    try {
      await apiRequest('/auth/mfa/confirm', {
        method: 'POST',
        headers: requestHeaders,
        body: JSON.stringify({ code }),
      })
      await onComplete()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to verify the code.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="auth-shell">
      <Card className="auth-card">
        <Text className="eyebrow auth-eyebrow">ACCOUNT SECURITY</Text>
        <Title level={2}>Set up authenticator MFA</Title>
        <Text type="secondary">
          This account has access to identity administration. Configure an authenticator app before continuing.
        </Text>

        {error && <Alert className="auth-alert" type="error" showIcon title={error} />}

        {secret ? (
          <Space orientation="vertical" size="middle" className="auth-form">
            <Text>
              Add this key to your authenticator app, then enter the current code to verify setup.
            </Text>
            <Text code copyable>{secret}</Text>
            <Input
              size="large"
              aria-label="Authenticator code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/[^0-9]/g, ''))}
              placeholder="6-digit code"
            />
            <Button type="primary" size="large" block loading={saving} onClick={() => void confirmSetup()}>
              Verify and enable MFA
            </Button>
          </Space>
        ) : (
          <Button type="primary" size="large" block loading={saving} onClick={() => void startSetup()}>
            Generate authenticator key
          </Button>
        )}
      </Card>
    </div>
  )
}

export default MfaSetup
