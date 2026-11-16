import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  CalendarOutlined,
  DollarOutlined,
  FileSearchOutlined,
  HeartOutlined,
  HomeOutlined,
  MedicineBoxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  TeamOutlined,
  UserAddOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  ConfigProvider,
  Dropdown,
  Input,
  Layout,
  Menu,
  Space,
  Typography,
} from 'antd'
import type { MenuProps } from 'antd'
import AdminConsole from './AdminConsole'
import { apiRequest } from './api'
import PatientAccess from './PatientAccess'
import type { AuthUser } from './api'
import './App.css'

const { Header, Sider, Content } = Layout
const { Text, Title } = Typography
const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME ?? 'tether_csrf'

type NavigationLink = {
  key: string
  icon: ReactNode
  label: string
  permissions: string[]
}

type NavigationSection = {
  label?: string
  items: NavigationLink[]
}

const navigationSections: NavigationSection[] = [
  {
    items: [
      {
        key: 'overview',
        icon: <AppstoreOutlined />,
        label: 'Overview',
        permissions: ['administration.operational-dashboards-and-reports.view'],
      },
    ],
  },
  {
    label: 'PATIENT ACCESS',
    items: [
      { key: 'patient-register', icon: <UserAddOutlined />, label: 'Patient register', permissions: ['front-office.patient-registration-and-biodata.view'] },
      { key: 'patient-queue', icon: <TeamOutlined />, label: 'Patient queue', permissions: ['front-office.open-outpatient-visit.view'] },
      { key: 'appointments', icon: <CalendarOutlined />, label: 'Appointments', permissions: ['front-office.appointment-scheduling.view', 'patient-services.request-appointments-update-contact-details.view'] },
      { key: 'admissions', icon: <HomeOutlined />, label: 'Admissions', permissions: ['clinical.admission-transfer-and-discharge-orders.view'] },
    ],
  },
  {
    label: 'CARE DELIVERY',
    items: [
      { key: 'nursing', icon: <HeartOutlined />, label: 'Nursing', permissions: ['nursing.triage-and-vital-signs.view', 'nursing.nursing-notes-and-care-plans.view'] },
      { key: 'doctors', icon: <MedicineBoxOutlined />, label: 'Doctors', permissions: ['clinical.consultation-notes-and-examination.view'] },
      { key: 'diagnostics', icon: <FileSearchOutlined />, label: 'Laboratory & imaging', permissions: ['laboratory.laboratory-requests-and-worklists.view', 'radiology.imaging-requests-and-schedule.view'] },
      { key: 'wards', icon: <HomeOutlined />, label: 'Ward management', permissions: ['nursing.ward-observations-and-fluid-charts.view', 'nursing.nursing-documentation-review.view'] },
      { key: 'pharmacy', icon: <MedicineBoxOutlined />, label: 'Pharmacy & stock', permissions: ['pharmacy.view-prescriptions.view', 'pharmacy.medication-stock-and-batch-records.view'] },
    ],
  },
  {
    label: 'OPERATIONS',
    items: [
      { key: 'billing', icon: <DollarOutlined />, label: 'Billing & cashier', permissions: ['billing.view-patient-charges-and-account.view', 'cash-office.receive-cash-m-pesa-card-payments.view'] },
      { key: 'accounting', icon: <AuditOutlined />, label: 'Accounting', permissions: ['accounts.view-financial-transactions-and-reports.view'] },
      { key: 'people', icon: <TeamOutlined />, label: 'Staff & rosters', permissions: ['human-resources.staff-records-and-employment-details.view'] },
      { key: 'reports', icon: <FileSearchOutlined />, label: 'Reports', permissions: ['medical-records.medical-statistics-and-records-reports.view', 'quality-audit.quality-indicators-and-incident-reports.view', 'quality-audit.read-only-audit-trail-and-transaction-reports.view'] },
    ],
  },
]

const menuLabels = new Map<string, string>([
  ['overview', 'Overview'],
  ['patient-register', 'Patient register'],
  ['patient-queue', 'Patient queue'],
  ['appointments', 'Appointments'],
  ['admissions', 'Admissions'],
  ['nursing', 'Nursing'],
  ['doctors', 'Doctors'],
  ['diagnostics', 'Laboratory & imaging'],
  ['wards', 'Ward management'],
  ['pharmacy', 'Pharmacy & stock'],
  ['billing', 'Billing & cashier'],
  ['accounting', 'Accounting'],
  ['people', 'Staff & rosters'],
  ['reports', 'Reports'],
  ['settings', 'Administration & audit'],
])

function hasPermission(user: AuthUser, permissionKeys: string[]) {
  return permissionKeys.some((permission) => user.permissions.includes(permission))
}

function canOpenNavigationKey(user: AuthUser, key: string) {
  if (key === 'settings') {
    return hasPermission(user, [
      'identity.users.manage',
      'identity.roles.manage',
      'quality-audit.read-only-audit-trail-and-transaction-reports.view',
    ])
  }
  return navigationSections
    .flatMap((section) => section.items)
    .some((item) => item.key === key && hasPermission(user, item.permissions))
}

function buildNavigation(user: AuthUser): MenuProps['items'] {
  const items: NonNullable<MenuProps['items']> = []
  for (const section of navigationSections) {
    const links = section.items
      .filter((item) => hasPermission(user, item.permissions))
      .map(({ key, icon, label }) => ({ key, icon, label }))
    if (section.label && links.length) {
      items.push({ type: 'group', label: section.label, children: links })
    } else {
      items.push(...links)
    }
  }
  if (canOpenNavigationKey(user, 'settings')) {
    items.push({ key: 'settings', icon: <SettingOutlined />, label: 'Administration & audit' })
  }
  return items
}

function defaultNavigationKey(user: AuthUser) {
  if (canOpenNavigationKey(user, 'patient-queue')) return 'patient-queue'
  if (canOpenNavigationKey(user, 'settings')) return 'settings'
  return navigationSections
    .flatMap((section) => section.items)
    .find((item) => hasPermission(user, item.permissions))?.key ?? 'no-access'
}

function readCsrfCookie() {
  const cookie = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${CSRF_COOKIE_NAME}=`))
  return cookie ? decodeURIComponent(cookie.slice(CSRF_COOKIE_NAME.length + 1)) : ''
}

function App() {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 992)
  const [selectedKey, setSelectedKey] = useState('patient-queue')
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [csrfToken, setCsrfToken] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loginState, setLoginState] = useState({ username: '', password: '' })
  const [submitting, setSubmitting] = useState(false)
  const navigationItems = useMemo(
    () => (authUser ? buildNavigation(authUser) : []),
    [authUser],
  )

  const loadCurrentUser = async () => {
    try {
      const user = await apiRequest<AuthUser>('/auth/me')
      setAuthUser(user)
      setCsrfToken(readCsrfCookie())
      setLoginError('')
    } catch (error) {
      setAuthUser(null)
      setCsrfToken('')
      setLoginError(
        error instanceof Error && error.message !== 'authentication_required'
          ? error.message
          : '',
      )
    } finally {
      setAuthLoading(false)
    }
  }

  useEffect(() => {
    const updateSidebar = () => setCollapsed(window.innerWidth < 992)
    window.addEventListener('resize', updateSidebar)
    return () => window.removeEventListener('resize', updateSidebar)
  }, [])

  useEffect(() => {
    void loadCurrentUser()
  }, [])

  useEffect(() => {
    if (authUser && !canOpenNavigationKey(authUser, selectedKey)) {
      setSelectedKey(defaultNavigationKey(authUser))
    }
  }, [authUser, selectedKey])

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setLoginError('')

    try {
      const response = await apiRequest<{ csrf_token: string }>('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: loginState.username,
          password: loginState.password,
        }),
      })

      setCsrfToken(response.csrf_token)
      await loadCurrentUser()
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Unable to sign in.')
      setAuthUser(null)
    } finally {
      setSubmitting(false)
    }
  }

  const handleLogout = async () => {
    if (!csrfToken) {
      setAuthUser(null)
      return
    }

    try {
      await apiRequest('/auth/logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
    } catch {
      // ignore the logout response failure and clear the session in the UI
    } finally {
      setAuthUser(null)
      setCsrfToken('')
      setLoginState({ username: '', password: '' })
    }
  }

  const userMenu: MenuProps = {
    items: [
      { key: 'profile', label: 'My profile' },
      { key: 'signout', label: 'Sign out', onClick: handleLogout },
    ],
  }

  if (authLoading) {
    return (
      <div className="auth-shell">
        <Card className="auth-card">
          <Title level={3}>Loading TETHER...</Title>
        </Card>
      </div>
    )
  }

  if (!authUser) {
    return (
      <div className="auth-shell">
        <Card className="auth-card">
          <div className="auth-brand">
            <div className="brand-mark auth-brand-mark"><HeartOutlined /></div>
            <div>
              <Text className="eyebrow auth-eyebrow">SECURE ACCESS</Text>
              <Title level={2}>TETHER</Title>
            </div>
          </div>

          <Text type="secondary">Sign in with your hospital account to access the queue and patient workflows.</Text>

          {loginError && (
            <Alert className="auth-alert" type="error" showIcon title={loginError} />
          )}

          <form onSubmit={handleLogin} className="auth-form">
            <label className="auth-field">
              <span>Username</span>
              <Input
                size="large"
                value={loginState.username}
                onChange={(event) => setLoginState((current) => ({ ...current, username: event.target.value }))}
                placeholder="Enter username"
                autoComplete="username"
              />
            </label>

            <label className="auth-field">
              <span>Password</span>
              <Input.Password
                size="large"
                value={loginState.password}
                onChange={(event) => setLoginState((current) => ({ ...current, password: event.target.value }))}
                placeholder="Enter password"
                autoComplete="current-password"
              />
            </label>

            <Button type="primary" htmlType="submit" size="large" block loading={submitting}>
              Sign in
            </Button>
          </form>

          <Text type="secondary" className="auth-hint">
            Demo note: this prototype expects the FastAPI backend at http://localhost:8000.
          </Text>
        </Card>
      </div>
    )
  }

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#0f5c5c',
          colorSuccess: '#31845b',
          colorWarning: '#c88a15',
          colorError: '#c8463b',
          borderRadius: 8,
          fontFamily: 'Inter, "Segoe UI", sans-serif',
          fontSize: 13,
        },
      }}
    >
      <Layout className="app-layout">
        <Sider
          width={250}
          collapsedWidth={76}
          collapsed={collapsed}
          className="app-sider"
          breakpoint="lg"
          onBreakpoint={setCollapsed}
        >
          <div className="brand">
            <div className="brand-mark"><HeartOutlined /></div>
            {!collapsed && (
              <span className="brand-name">
                <strong>TETHER</strong>
                <small>HOSPITAL SYSTEM</small>
              </span>
            )}
          </div>
          <div className="facility-switch">
            <Text className="facility-label">FACILITY</Text>
            <Button block className="facility-button">
              <HomeOutlined />
              {!collapsed && <span>Central Hospital</span>}
            </Button>
          </div>
          <Menu
            mode="inline"
            items={navigationItems}
            selectedKeys={[selectedKey]}
            onClick={({ key }) => setSelectedKey(key)}
            className="main-menu"
          />
          {!collapsed && (
            <div className="sider-footer">
              <div className="connection-dot" />
              <span>System status</span>
              <strong>Online</strong>
            </div>
          )}
        </Sider>

        <Layout className="workspace">
          <Header className="top-header">
            <Space size={14}>
              <Button
                type="text"
                aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed(!collapsed)}
              />
              <div className="breadcrumb">
                <Text type="secondary">Patient access</Text>
                <span>/</span>
                <Text strong>{menuLabels.get(selectedKey) ?? 'Patient queue'}</Text>
              </div>
            </Space>
            <Space size={18}>
              <Text className="header-date">Friday, 13 November 2026</Text>
              <Badge count={3} size="small">
                <Button type="text" shape="circle" icon={<BellOutlined />} aria-label="Notifications" />
              </Badge>
              <Dropdown menu={userMenu} trigger={['click']}>
                <Button type="text" className="user-button">
                  <Avatar size="small" className="user-avatar">{authUser.username.slice(0, 2).toUpperCase()}</Avatar>
                  <span className="user-name">{authUser.username}</span>
                </Button>
              </Dropdown>
            </Space>
          </Header>

          <Content className="page-content">
            {selectedKey === 'settings' ? (
              <AdminConsole
                csrfToken={csrfToken}
                currentUserId={authUser.id}
                canManageUsers={hasPermission(authUser, ['identity.users.manage'])}
                canManageRoles={authUser.is_system_owner || authUser.roles.includes('SuperAdmin')}
                canViewAudit={hasPermission(authUser, [
                  'quality-audit.read-only-audit-trail-and-transaction-reports.view',
                ])}
                onSessionRevoked={() => void handleLogout()}
              />
            ) : selectedKey === 'patient-queue' || selectedKey === 'patient-register' ? (
              <PatientAccess
                mode={selectedKey === 'patient-register' ? 'register' : 'queue'}
                csrfToken={csrfToken}
                canSearchPatients={hasPermission(authUser, [
                  'front-office.search-existing-patient-records.view',
                ])}
                canCreatePatient={hasPermission(authUser, [
                  'front-office.patient-registration-and-biodata.add',
                ])}
                canEditPatient={hasPermission(authUser, [
                  'front-office.patient-registration-and-biodata.edit',
                ])}
                canOpenVisit={hasPermission(authUser, ['front-office.open-outpatient-visit.add'])}
                onShowRegister={() => setSelectedKey('patient-register')}
                onOpenQueue={() => setSelectedKey('patient-queue')}
              />
            ) : (
              <div className="module-placeholder">
                <div className="page-heading">
                  <div>
                    <Text className="eyebrow">ROLE-BASED ACCESS</Text>
                    <Title level={3}>{menuLabels.get(selectedKey) ?? 'No modules assigned'}</Title>
                    <Text type="secondary">
                      {selectedKey === 'no-access'
                        ? 'No modules are assigned to your account. Contact a system administrator.'
                        : 'You have access to this module, but its workflow is not implemented yet.'}
                    </Text>
                  </div>
                </div>
                <Alert
                  showIcon
                  type="info"
                  title="Access is controlled by your assigned roles. This module will not display sample patient data."
                />
              </div>
            )}
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}

export default App
