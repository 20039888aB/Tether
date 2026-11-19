import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  apiRequest,
  SYSTEM_DATA_CHANGED_EVENT,
  SYSTEM_MANUAL_REFRESH_EVENT,
} from './api'
import type { SystemEvent } from './api'

const { Text, Title } = Typography

type PatientRecord = {
  id: string
  patient_number: string
  first_name: string
  middle_name: string | null
  last_name: string
  date_of_birth: string | null
  sex_at_birth: string | null
  phone_number: string | null
  email: string | null
  address: string | null
  next_of_kin_name: string | null
  next_of_kin_phone: string | null
  next_of_kin_relationship: string | null
  next_of_kin_relationship_other: string | null
  version: number
  created_at: string | null
  updated_at: string | null
}

type PatientPage = {
  items: PatientRecord[]
  total: number
  limit: number
  offset: number
}

type VisitRecord = {
  id: string
  patient_id: string
  patient_number: string
  patient_name: string
  visit_number: string
  clinic: string
  visit_type: string
  status: string
  workflow_state: string
  created_at: string | null
}

type VisitPage = {
  items: VisitRecord[]
  total: number
  limit: number
  offset: number
}

type PatientForm = {
  first_name: string
  middle_name: string
  last_name: string
  date_of_birth: string
  sex_at_birth: string | null
  phone_number: string
  email: string
  address: string
  next_of_kin_name: string
  next_of_kin_phone: string
  next_of_kin_relationship: string | null
  next_of_kin_relationship_other: string
}

type PatientAccessProps = {
  mode: 'register' | 'queue'
  csrfToken: string
  canSearchPatients: boolean
  canCreatePatient: boolean
  canEditPatient: boolean
  canOpenVisit: boolean
  onShowRegister: () => void
  onOpenQueue: () => void
}

const EMPTY_FORM: PatientForm = {
  first_name: '',
  middle_name: '',
  last_name: '',
  date_of_birth: '',
  sex_at_birth: null,
  phone_number: '',
  email: '',
  address: '',
  next_of_kin_name: '',
  next_of_kin_phone: '',
  next_of_kin_relationship: null,
  next_of_kin_relationship_other: '',
}

const NEXT_OF_KIN_RELATIONSHIPS = [
  { label: 'Spouse', value: 'spouse' },
  { label: 'Partner', value: 'partner' },
  { label: 'Parent', value: 'parent' },
  { label: 'Mother', value: 'mother' },
  { label: 'Father', value: 'father' },
  { label: 'Child', value: 'child' },
  { label: 'Son', value: 'son' },
  { label: 'Daughter', value: 'daughter' },
  { label: 'Sibling', value: 'sibling' },
  { label: 'Brother', value: 'brother' },
  { label: 'Sister', value: 'sister' },
  { label: 'Grandparent', value: 'grandparent' },
  { label: 'Grandmother', value: 'grandmother' },
  { label: 'Grandfather', value: 'grandfather' },
  { label: 'Grandchild', value: 'grandchild' },
  { label: 'Aunt', value: 'aunt' },
  { label: 'Uncle', value: 'uncle' },
  { label: 'Niece', value: 'niece' },
  { label: 'Nephew', value: 'nephew' },
  { label: 'Cousin', value: 'cousin' },
  { label: 'Step-parent', value: 'step_parent' },
  { label: 'Step-child', value: 'step_child' },
  { label: 'Parent-in-law', value: 'parent_in_law' },
  { label: 'Child-in-law', value: 'child_in_law' },
  { label: 'Sibling-in-law', value: 'sibling_in_law' },
  { label: 'Guardian', value: 'guardian' },
  { label: 'Legal guardian', value: 'legal_guardian' },
  { label: 'Foster parent', value: 'foster_parent' },
  { label: 'Caregiver', value: 'caregiver' },
  { label: 'Friend', value: 'friend' },
  { label: 'Neighbor', value: 'neighbor' },
  { label: 'Other', value: 'other' },
]

function requestHeaders(csrfToken: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }
}

function PatientAccess({
  mode,
  csrfToken,
  canSearchPatients,
  canCreatePatient,
  canEditPatient,
  canOpenVisit,
  onShowRegister,
  onOpenQueue,
}: PatientAccessProps) {
  const [patientPage, setPatientPage] = useState<PatientPage>({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  })
  const [visitPage, setVisitPage] = useState<VisitPage>({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  })
  const [query, setQuery] = useState('')
  const [searchText, setSearchText] = useState('')
  const [patientOffset, setPatientOffset] = useState(0)
  const [visitOffset, setVisitOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [patientForm, setPatientForm] = useState<PatientForm>(EMPTY_FORM)
  const [editingPatient, setEditingPatient] = useState<PatientRecord | null>(null)
  const [visitPatient, setVisitPatient] = useState<PatientRecord | null>(null)
  const [clinic, setClinic] = useState('')
  const [visitType, setVisitType] = useState('Consultation')

  const loadPatients = useCallback(async () => {
    if (!canSearchPatients) return
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: '50', offset: String(patientOffset) })
      if (query) params.set('q', query)
      setPatientPage(await apiRequest<PatientPage>(`/patients?${params.toString()}`))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load patient records.')
    } finally {
      setLoading(false)
    }
  }, [canSearchPatients, patientOffset, query])

  const loadVisits = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({
        status: 'queued',
        limit: '50',
        offset: String(visitOffset),
      })
      setVisitPage(await apiRequest<VisitPage>(`/outpatient-visits?${params.toString()}`))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load the OPD queue.')
    } finally {
      setLoading(false)
    }
  }, [visitOffset])

  useEffect(() => {
    if (mode === 'register') void loadPatients()
    else void loadVisits()
  }, [loadPatients, loadVisits, mode])

  useEffect(() => {
    const refreshVisibleData = () => {
      if (mode === 'register') void loadPatients()
      else void loadVisits()
    }
    const handleDataChanged = (event: Event) => {
      if (!(event instanceof CustomEvent)) return
      const changedEvents = event.detail as SystemEvent[]
      const categories = new Set(changedEvents.map((change) => change.category))
      const relevantCategories =
        mode === 'register'
          ? ['patient_access']
          : ['patient_access', 'nursing', 'clinical']
      if (relevantCategories.some((category) => categories.has(category))) {
        refreshVisibleData()
      }
    }

    window.addEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
    window.addEventListener(SYSTEM_MANUAL_REFRESH_EVENT, refreshVisibleData)
    return () => {
      window.removeEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
      window.removeEventListener(SYSTEM_MANUAL_REFRESH_EVENT, refreshVisibleData)
    }
  }, [loadPatients, loadVisits, mode])

  const savePatient = async () => {
    setError('')
    setSuccess('')
    if (!patientForm.first_name.trim() || !patientForm.last_name.trim()) {
      setError('First name and last name are required.')
      return
    }
    const hasNextOfKinDetails = Boolean(
      patientForm.next_of_kin_name.trim() ||
      patientForm.next_of_kin_phone.trim() ||
      patientForm.next_of_kin_relationship,
    )
    if (
      hasNextOfKinDetails &&
      (!patientForm.next_of_kin_name.trim() ||
        !patientForm.next_of_kin_phone.trim() ||
        !patientForm.next_of_kin_relationship)
    ) {
      setError('Enter the next-of-kin name, phone and relationship together.')
      return
    }
    if (
      patientForm.next_of_kin_relationship === 'other' &&
      !patientForm.next_of_kin_relationship_other.trim()
    ) {
      setError('Specify the next-of-kin relationship when Other is selected.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        ...patientForm,
        first_name: patientForm.first_name.trim(),
        middle_name: patientForm.middle_name.trim() || null,
        last_name: patientForm.last_name.trim(),
        date_of_birth: patientForm.date_of_birth || null,
        phone_number: patientForm.phone_number.trim() || null,
        email: patientForm.email.trim() || null,
        address: patientForm.address.trim() || null,
        next_of_kin_name: patientForm.next_of_kin_name.trim() || null,
        next_of_kin_phone: patientForm.next_of_kin_phone.trim() || null,
        next_of_kin_relationship: patientForm.next_of_kin_relationship,
        next_of_kin_relationship_other:
          patientForm.next_of_kin_relationship === 'other'
            ? patientForm.next_of_kin_relationship_other.trim() || null
            : null,
        ...(editingPatient ? { version: editingPatient.version } : {}),
      }
      const result = await apiRequest<PatientRecord>(
        editingPatient ? `/patients/${editingPatient.id}` : '/patients',
        {
          method: editingPatient ? 'PUT' : 'POST',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify(payload),
        },
      )
      setSuccess(
        editingPatient
          ? `Patient ${result.patient_number} updated.`
          : `Patient registered. TETHER number: ${result.patient_number}.`,
      )
      setEditingPatient(null)
      setPatientForm(EMPTY_FORM)
      if (canSearchPatients) await loadPatients()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save patient record.')
    } finally {
      setSaving(false)
    }
  }

  const openVisit = async () => {
    if (!visitPatient) return
    setError('')
    setSuccess('')
    if (!clinic.trim() || !visitType.trim()) {
      setError('Clinic and visit type are required.')
      return
    }
    setSaving(true)
    try {
      const visit = await apiRequest<VisitRecord>('/outpatient-visits', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          patient_id: visitPatient.id,
          clinic: clinic.trim(),
          visit_type: visitType.trim(),
        }),
      })
      setVisitPatient(null)
      setClinic('')
      setVisitType('Consultation')
      setSuccess(`OPD visit ${visit.visit_number} added to the queue.`)
      onOpenQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to open OPD visit.')
    } finally {
      setSaving(false)
    }
  }

  const patientColumns: TableColumnsType<PatientRecord> = [
    {
      title: 'PATIENT',
      key: 'name',
      render: (_, patient) => (
        <span className="patient-cell">
          <Text strong>{[patient.first_name, patient.middle_name, patient.last_name].filter(Boolean).join(' ')}</Text>
          <Text type="secondary">{patient.patient_number}</Text>
        </span>
      ),
    },
    {
      title: 'DATE OF BIRTH',
      dataIndex: 'date_of_birth',
      key: 'date_of_birth',
      render: (value: string | null) => value ?? '—',
    },
    { title: 'SEX', dataIndex: 'sex_at_birth', key: 'sex_at_birth', render: (value: string | null) => value ?? '—' },
    { title: 'PHONE', dataIndex: 'phone_number', key: 'phone_number', render: (value: string | null) => value ?? '—' },
    {
      title: '',
      key: 'actions',
      align: 'right',
      render: (_, patient) => (
        <Space>
          {canEditPatient && (
            <Button
              onClick={() => {
                setEditingPatient(patient)
                setPatientForm({
                  first_name: patient.first_name,
                  middle_name: patient.middle_name ?? '',
                  last_name: patient.last_name,
                  date_of_birth: patient.date_of_birth ?? '',
                  sex_at_birth: patient.sex_at_birth,
                  phone_number: patient.phone_number ?? '',
                  email: patient.email ?? '',
                  address: patient.address ?? '',
                  next_of_kin_name: patient.next_of_kin_name ?? '',
                  next_of_kin_phone: patient.next_of_kin_phone ?? '',
                  next_of_kin_relationship: patient.next_of_kin_relationship,
                  next_of_kin_relationship_other:
                    patient.next_of_kin_relationship_other ?? '',
                })
              }}
            >
              Edit
            </Button>
          )}
          {canOpenVisit && (
            <Button
              type="primary"
              onClick={() => {
                setVisitPatient(patient)
                setClinic('')
                setVisitType('Consultation')
              }}
            >
              Open OPD visit
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const visitColumns: TableColumnsType<VisitRecord> = [
    {
      title: 'PATIENT',
      key: 'patient',
      render: (_, visit) => (
        <span className="patient-cell">
          <Text strong>{visit.patient_name}</Text>
          <Text type="secondary">{visit.patient_number}</Text>
        </span>
      ),
    },
    { title: 'VISIT NO.', dataIndex: 'visit_number', key: 'visit_number' },
    { title: 'CLINIC', dataIndex: 'clinic', key: 'clinic' },
    { title: 'VISIT TYPE', dataIndex: 'visit_type', key: 'visit_type' },
    {
      title: 'ARRIVED',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string | null) => value ? new Date(value).toLocaleString() : '—',
    },
    {
      title: 'STATUS',
      dataIndex: 'status',
      key: 'status',
      render: (_, visit) => <Tag color="gold">{visit.workflow_state.replaceAll('_', ' ')}</Tag>,
    },
  ]

  const patientFormFields = (
    <div className="admin-form-grid">
      <Input
        aria-label="First name"
        placeholder="First name *"
        value={patientForm.first_name}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, first_name: event.target.value }))
        }
      />
      <Input
        aria-label="Middle name"
        placeholder="Middle name"
        value={patientForm.middle_name}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, middle_name: event.target.value }))
        }
      />
      <Input
        aria-label="Last name"
        placeholder="Last name *"
        value={patientForm.last_name}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, last_name: event.target.value }))
        }
      />
      <Input
        aria-label="Date of birth"
        type="date"
        value={patientForm.date_of_birth}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, date_of_birth: event.target.value }))
        }
      />
      <Select
        aria-label="Sex at birth"
        allowClear
        placeholder="Sex at birth"
        value={patientForm.sex_at_birth}
        onChange={(value) => setPatientForm((form) => ({ ...form, sex_at_birth: value ?? null }))}
        options={[
          { label: 'Female', value: 'female' },
          { label: 'Male', value: 'male' },
          { label: 'Intersex', value: 'intersex' },
          { label: 'Unknown', value: 'unknown' },
        ]}
      />
      <Input
        aria-label="Phone number"
        placeholder="Phone number"
        value={patientForm.phone_number}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, phone_number: event.target.value }))
        }
      />
      <Input
        aria-label="Email"
        type="email"
        placeholder="Email"
        value={patientForm.email}
        onChange={(event) => setPatientForm((form) => ({ ...form, email: event.target.value }))}
      />
      <Input
        aria-label="Address"
        placeholder="Address"
        value={patientForm.address}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, address: event.target.value }))
        }
      />
      <Text strong style={{ gridColumn: '1 / -1' }}>Next of kin (optional)</Text>
      <Input
        aria-label="Next-of-kin name"
        placeholder="Next-of-kin name"
        value={patientForm.next_of_kin_name}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, next_of_kin_name: event.target.value }))
        }
      />
      <Input
        aria-label="Next-of-kin phone"
        placeholder="Next-of-kin phone"
        value={patientForm.next_of_kin_phone}
        onChange={(event) =>
          setPatientForm((form) => ({ ...form, next_of_kin_phone: event.target.value }))
        }
      />
      <Select
        aria-label="Next-of-kin relationship"
        allowClear
        placeholder="Next-of-kin relationship"
        value={patientForm.next_of_kin_relationship}
        onChange={(value) =>
          setPatientForm((form) => ({
            ...form,
            next_of_kin_relationship: value ?? null,
            next_of_kin_relationship_other:
              value === 'other' ? form.next_of_kin_relationship_other : '',
          }))
        }
        options={NEXT_OF_KIN_RELATIONSHIPS}
      />
      {patientForm.next_of_kin_relationship === 'other' && (
        <Input
          aria-label="Specify next-of-kin relationship"
          placeholder="Specify relationship *"
          value={patientForm.next_of_kin_relationship_other}
          onChange={(event) =>
            setPatientForm((form) => ({
              ...form,
              next_of_kin_relationship_other: event.target.value,
            }))
          }
        />
      )}
    </div>
  )

  return (
    <div className="patient-access">
      <div className="page-heading">
        <div>
          <Text className="eyebrow">PATIENT ACCESS</Text>
          <Title level={3}>{mode === 'register' ? 'Patient registration' : 'OPD queue'}</Title>
          <Text type="secondary">
            {mode === 'register'
              ? 'Register and search persisted patient records, then open an outpatient visit.'
              : 'Review outpatient visits currently waiting in the queue.'}
          </Text>
        </div>
        {mode === 'queue' && canSearchPatients && (
          <Button type="primary" onClick={onShowRegister}>Find patient</Button>
        )}
      </div>

      <Alert
        showIcon
        type="warning"
        title="Development workflow only. Use synthetic data; registration fields and duplicate-review policy require hospital approval before real patient data is used."
        className="admin-notice"
      />
      {error && <Alert showIcon type="error" title={error} className="admin-notice" />}
      {success && <Alert showIcon type="success" title={success} className="admin-notice" />}

      {mode === 'register' ? (
        <Space orientation="vertical" size={18} className="admin-content">
          {canCreatePatient && (
            <Card size="small" title="Register patient">
              <Space orientation="vertical" className="modal-full-width">
                {patientFormFields}
                <Button type="primary" loading={saving} onClick={() => void savePatient()}>
                  Register patient
                </Button>
              </Space>
            </Card>
          )}
          {canSearchPatients ? (
            <Card size="small" title="Patient records">
              <div className="queue-toolbar">
                <Input.Search
                  allowClear
                  aria-label="Search patients"
                  placeholder="Search name, patient number or phone"
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  onSearch={(value) => {
                    setPatientOffset(0)
                    setQuery(value.trim())
                  }}
                  className="queue-search"
                />
              </div>
              <Table
                columns={patientColumns}
                dataSource={patientPage.items}
                loading={loading}
                rowKey="id"
                pagination={{
                  current: Math.floor(patientPage.offset / patientPage.limit) + 1,
                  pageSize: patientPage.limit,
                  total: patientPage.total,
                  onChange: (page, pageSize) => setPatientOffset((page - 1) * pageSize),
                }}
                scroll={{ x: 900 }}
              />
            </Card>
          ) : !canCreatePatient ? (
            <Alert showIcon type="warning" title="Your account can open this screen but does not have patient search or registration privileges." />
          ) : null}
        </Space>
      ) : (
        <Card size="small" title="Outpatient visits waiting">
          <Table
            columns={visitColumns}
            dataSource={visitPage.items}
            loading={loading}
            rowKey="id"
            pagination={{
              current: Math.floor(visitPage.offset / visitPage.limit) + 1,
              pageSize: visitPage.limit,
              total: visitPage.total,
              onChange: (page, pageSize) => setVisitOffset((page - 1) * pageSize),
            }}
            scroll={{ x: 900 }}
          />
        </Card>
      )}

      <Modal
        title={`Edit patient: ${editingPatient?.patient_number ?? ''}`}
        open={editingPatient !== null}
        onCancel={() => {
          setEditingPatient(null)
          setPatientForm(EMPTY_FORM)
        }}
        onOk={() => void savePatient()}
        confirmLoading={saving}
        okText="Save patient"
      >
        {patientFormFields}
      </Modal>

      <Modal
        title={`Open OPD visit: ${visitPatient?.patient_number ?? ''}`}
        open={visitPatient !== null}
        onCancel={() => setVisitPatient(null)}
        onOk={() => void openVisit()}
        confirmLoading={saving}
        okText="Add to queue"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Clinic"
            placeholder="Clinic *"
            value={clinic}
            onChange={(event) => setClinic(event.target.value)}
          />
          <Input
            aria-label="Visit type"
            placeholder="Visit type *"
            value={visitType}
            onChange={(event) => setVisitType(event.target.value)}
          />
        </Space>
      </Modal>
    </div>
  )
}

export default PatientAccess
