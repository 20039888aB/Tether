import { useEffect, useMemo, useState } from 'react'
import {
  AppstoreOutlined,
  AuditOutlined,
  BellOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  FileSearchOutlined,
  HeartOutlined,
  HomeOutlined,
  MedicineBoxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
  UserAddOutlined,
  UserOutlined,
} from '@ant-design/icons'
import {
  Avatar,
  Badge,
  Button,
  Card,
  ConfigProvider,
  Dropdown,
  Input,
  Layout,
  Menu,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { MenuProps, TableColumnsType } from 'antd'
import './App.css'

const { Header, Sider, Content } = Layout
const { Text, Title } = Typography

type QueuePatient = {
  key: string
  name: string
  patientNumber: string
  visitNumber: string
  clinic: string
  visitType: string
  queuedAt: string
  waitMinutes: number
  status: 'Queued' | 'Triaged' | 'With nurse' | 'With doctor'
  assignedTo: string
}

const queuePatients: QueuePatient[] = [
  { key: '1', name: 'Amina Njeri', patientNumber: 'HMS-004821', visitNumber: 'V-2026-0136', clinic: 'Outpatient', visitType: 'Consultation', queuedAt: '08:42', waitMinutes: 34, status: 'With nurse', assignedTo: 'N. Kamau' },
  { key: '2', name: 'Brian Otieno', patientNumber: 'HMS-004820', visitNumber: 'V-2026-0135', clinic: 'Paediatrics', visitType: 'Review', queuedAt: '08:51', waitMinutes: 25, status: 'Triaged', assignedTo: '—' },
  { key: '3', name: 'Wanjiku Mwangi', patientNumber: 'HMS-004819', visitNumber: 'V-2026-0134', clinic: 'General practice', visitType: 'Consultation', queuedAt: '09:03', waitMinutes: 13, status: 'Queued', assignedTo: '—' },
  { key: '4', name: 'David Kiptoo', patientNumber: 'HMS-004818', visitNumber: 'V-2026-0133', clinic: 'Dental', visitType: 'New visit', queuedAt: '09:06', waitMinutes: 10, status: 'With doctor', assignedTo: 'Dr. M. Wekesa' },
  { key: '5', name: 'Grace Achieng', patientNumber: 'HMS-004817', visitNumber: 'V-2026-0132', clinic: 'Outpatient', visitType: 'Consultation', queuedAt: '09:12', waitMinutes: 4, status: 'Queued', assignedTo: '—' },
  { key: '6', name: 'Peter Maina', patientNumber: 'HMS-004816', visitNumber: 'V-2026-0131', clinic: 'Antenatal care', visitType: 'Follow-up', queuedAt: '09:14', waitMinutes: 2, status: 'Triaged', assignedTo: '—' },
]

const navigation: MenuProps['items'] = [
  { key: 'overview', icon: <AppstoreOutlined />, label: 'Overview' },
  {
    key: 'patients-group',
    type: 'group',
    label: 'PATIENT ACCESS',
    children: [
      { key: 'patient-register', icon: <UserAddOutlined />, label: 'Patient register' },
      { key: 'patient-queue', icon: <TeamOutlined />, label: 'Patient queue' },
      { key: 'appointments', icon: <CalendarOutlined />, label: 'Appointments' },
      { key: 'admissions', icon: <HomeOutlined />, label: 'Admissions' },
    ],
  },
  {
    key: 'care-group',
    type: 'group',
    label: 'CARE DELIVERY',
    children: [
      { key: 'nursing', icon: <HeartOutlined />, label: 'Nursing' },
      { key: 'doctors', icon: <MedicineBoxOutlined />, label: 'Doctors' },
      { key: 'diagnostics', icon: <FileSearchOutlined />, label: 'Laboratory & imaging' },
      { key: 'wards', icon: <HomeOutlined />, label: 'Ward management' },
      { key: 'pharmacy', icon: <MedicineBoxOutlined />, label: 'Pharmacy & stock' },
    ],
  },
  {
    key: 'operations-group',
    type: 'group',
    label: 'OPERATIONS',
    children: [
      { key: 'billing', icon: <DollarOutlined />, label: 'Billing & cashier' },
      { key: 'accounting', icon: <AuditOutlined />, label: 'Accounting' },
      { key: 'people', icon: <TeamOutlined />, label: 'Staff & rosters' },
      { key: 'reports', icon: <FileSearchOutlined />, label: 'Reports' },
    ],
  },
  { key: 'settings', icon: <SettingOutlined />, label: 'Administration' },
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
  ['settings', 'Administration'],
])

function statusColor(status: QueuePatient['status']) {
  switch (status) {
    case 'Queued':
      return 'default'
    case 'Triaged':
      return 'gold'
    case 'With nurse':
      return 'blue'
    case 'With doctor':
      return 'green'
  }
}

function App() {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 992)
  const [selectedKey, setSelectedKey] = useState('patient-queue')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => {
    const updateSidebar = () => setCollapsed(window.innerWidth < 992)
    window.addEventListener('resize', updateSidebar)
    return () => window.removeEventListener('resize', updateSidebar)
  }, [])

  const filteredPatients = useMemo(() => queuePatients.filter((patient) => {
    const matchesQuery = `${patient.name} ${patient.patientNumber} ${patient.visitNumber} ${patient.clinic}`
      .toLowerCase()
      .includes(query.toLowerCase())
    return matchesQuery && (statusFilter === 'all' || patient.status === statusFilter)
  }), [query, statusFilter])

  const columns: TableColumnsType<QueuePatient> = [
    {
      title: 'PATIENT',
      dataIndex: 'name',
      key: 'patient',
      width: 250,
      render: (_, patient) => (
        <Space size={12}>
          <Avatar className="patient-avatar" icon={<UserOutlined />} />
          <span className="patient-cell">
            <Text strong>{patient.name}</Text>
            <Text type="secondary">{patient.patientNumber}</Text>
          </span>
        </Space>
      ),
    },
    { title: 'VISIT NO.', dataIndex: 'visitNumber', key: 'visitNumber', width: 150 },
    {
      title: 'CLINIC / VISIT',
      key: 'clinic',
      width: 220,
      render: (_, patient) => (
        <span className="patient-cell">
          <Text>{patient.clinic}</Text>
          <Text type="secondary">{patient.visitType}</Text>
        </span>
      ),
    },
    {
      title: 'QUEUE TIME',
      dataIndex: 'queuedAt',
      key: 'queuedAt',
      width: 140,
      sorter: (left, right) => left.queuedAt.localeCompare(right.queuedAt),
    },
    {
      title: 'WAIT',
      dataIndex: 'waitMinutes',
      key: 'waitMinutes',
      width: 120,
      sorter: (left, right) => left.waitMinutes - right.waitMinutes,
      render: (minutes: number) => (
        <Space size={6} className={minutes >= 30 ? 'wait-long' : 'wait-normal'}>
          <ClockCircleOutlined />
          <Text>{minutes} min</Text>
        </Space>
      ),
    },
    {
      title: 'STATUS',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (status: QueuePatient['status']) => (
        <Tag color={statusColor(status)} className="status-tag">{status}</Tag>
      ),
    },
    { title: 'ASSIGNED TO', dataIndex: 'assignedTo', key: 'assignedTo', width: 170 },
    {
      title: '',
      key: 'action',
      width: 110,
      align: 'right',
      render: (_, patient) => (
        <Button type="link" onClick={() => setSelectedKey('patient-queue')} aria-label={`Open ${patient.name}`}>
          Open
        </Button>
      ),
    },
  ]

  const userMenu: MenuProps = {
    items: [
      { key: 'profile', label: 'My profile' },
      { key: 'signout', label: 'Sign out', disabled: true },
    ],
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
                <strong>CareGrid</strong>
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
            items={navigation}
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
                  <Avatar size="small" className="user-avatar">AM</Avatar>
                  <span className="user-name">Alex Morgan</span>
                </Button>
              </Dropdown>
            </Space>
          </Header>

          <Content className="page-content">
            <div className="page-heading">
              <div>
                <Text className="eyebrow">PATIENT ACCESS</Text>
                <Title level={3}>{menuLabels.get(selectedKey) ?? 'Patient queue'}</Title>
                <Text type="secondary">Review arrivals and follow each visit through the clinic.</Text>
              </div>
              <Space>
                <Button icon={<CalendarOutlined />}>Appointments</Button>
                <Button type="primary" icon={<PlusOutlined />}>Register patient</Button>
              </Space>
            </div>

            <div className="summary-grid">
              <Card className="summary-card">
                <Statistic title="In today’s queue" value={28} prefix={<TeamOutlined />} />
                <Text className="stat-footnote">Across 6 clinics</Text>
              </Card>
              <Card className="summary-card">
                <Statistic title="Waiting for triage" value={8} prefix={<ClockCircleOutlined />} />
                <Text className="stat-footnote">Median wait 12 min</Text>
              </Card>
              <Card className="summary-card">
                <Statistic title="With care team" value={14} prefix={<HeartOutlined />} />
                <Text className="stat-footnote">Nursing and doctor visits</Text>
              </Card>
              <Card className="summary-card">
                <Statistic title="Completed today" value={6} prefix={<CheckCircleOutlined />} />
                <Text className="stat-footnote">Updated just now</Text>
              </Card>
            </div>

            <Card className="queue-card" styles={{ body: { padding: 0 } }}>
              <div className="queue-toolbar">
                <div>
                  <Title level={5}>Live patient queue</Title>
                  <Text type="secondary">Queue updates will appear here as visits progress.</Text>
                </div>
                <Space wrap>
                  <Input
                    allowClear
                    prefix={<SearchOutlined />}
                    placeholder="Search patient, number or clinic"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    className="queue-search"
                  />
                  <Select
                    value={statusFilter}
                    onChange={setStatusFilter}
                    className="status-filter"
                    options={[
                      { value: 'all', label: 'All statuses' },
                      { value: 'Queued', label: 'Queued' },
                      { value: 'Triaged', label: 'Triaged' },
                      { value: 'With nurse', label: 'With nurse' },
                      { value: 'With doctor', label: 'With doctor' },
                    ]}
                  />
                  <Button icon={<SearchOutlined />}>Filters</Button>
                </Space>
              </div>
              <div className="queue-meta">
                <Text type="secondary"><span className="live-dot" /> Live board</Text>
                <Text type="secondary">Showing {filteredPatients.length} of 28 visits</Text>
              </div>
              <Table
                columns={columns}
                dataSource={filteredPatients}
                pagination={{ pageSize: 15, showSizeChanger: false, showTotal: (total, range) => `${range[0]}–${range[1]} of ${total} visits` }}
                scroll={{ x: 1120 }}
                size="middle"
                rowKey="key"
              />
            </Card>
            <div className="demo-notice">
              <Text type="secondary">Prototype workspace — all names and records shown are synthetic demo data.</Text>
            </div>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}

export default App
