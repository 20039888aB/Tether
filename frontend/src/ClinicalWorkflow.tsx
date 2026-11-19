import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Input,
  InputNumber,
  Modal,
  Space,
  Switch,
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
}

type VisitTriage = {
  blood_pressure_systolic: number | null
  blood_pressure_diastolic: number | null
  pulse_rate_bpm: number | null
  temperature_celsius: number | null
  respiratory_rate_bpm: number | null
  oxygen_saturation_percent: number | null
  weight_kg: number | null
  height_cm: number | null
  pain_score: number | null
  notes: string | null
  created_at: string | null
}

type ConsultationNote = {
  id: string
  parent_note_id: string | null
  note_type: 'consultation' | 'addendum'
  body: string
  status: 'draft' | 'signed'
  author_user_id: string
  version: number
  created_at: string | null
  signed_at: string | null
}

type ClinicalVisit = {
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
  patient: PatientRecord
  triage: VisitTriage | null
  consultation_notes: ConsultationNote[]
}

type QueuePage = {
  items: ClinicalVisit[]
  total: number
  limit: number
  offset: number
}

type TriageForm = Omit<VisitTriage, 'created_at'> & { notes: string }
type TriageNumberField = Exclude<keyof TriageForm, 'notes'>

type ClinicalWorkflowProps = {
  mode: 'nursing' | 'doctors'
  csrfToken: string
  currentUserId: string
}

const EMPTY_TRIAGE: TriageForm = {
  blood_pressure_systolic: null,
  blood_pressure_diastolic: null,
  pulse_rate_bpm: null,
  temperature_celsius: null,
  respiratory_rate_bpm: null,
  oxygen_saturation_percent: null,
  weight_kg: null,
  height_cm: null,
  pain_score: null,
  notes: '',
}

const TRIAGE_FIELDS: Array<{
  name: TriageNumberField
  label: string
  min: number
  max: number
  step?: number
}> = [
  { name: 'blood_pressure_systolic', label: 'Systolic BP (mmHg)', min: 40, max: 300 },
  { name: 'blood_pressure_diastolic', label: 'Diastolic BP (mmHg)', min: 20, max: 200 },
  { name: 'pulse_rate_bpm', label: 'Pulse (bpm)', min: 0, max: 300 },
  { name: 'temperature_celsius', label: 'Temperature (°C)', min: 25, max: 45, step: 0.1 },
  { name: 'respiratory_rate_bpm', label: 'Respiration (breaths/min)', min: 0, max: 100 },
  { name: 'oxygen_saturation_percent', label: 'Oxygen saturation (%)', min: 0, max: 100 },
  { name: 'weight_kg', label: 'Weight (kg)', min: 0.1, max: 500, step: 0.1 },
  { name: 'height_cm', label: 'Height (cm)', min: 0.1, max: 300, step: 0.1 },
  { name: 'pain_score', label: 'Pain score (0–10)', min: 0, max: 10 },
]

function requestHeaders(csrfToken: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }
}

function displayValue(value: string | number | null | undefined) {
  return value === null || value === undefined || value === '' ? '—' : value
}

function patientRelationship(patient: PatientRecord) {
  if (patient.next_of_kin_relationship === 'other') {
    return patient.next_of_kin_relationship_other ?? 'Other'
  }
  return patient.next_of_kin_relationship?.replaceAll('_', ' ') ?? '—'
}

function PatientDetails({ patient }: { patient: PatientRecord }) {
  return (
    <Descriptions size="small" column={1} bordered>
      <Descriptions.Item label="Patient number">{patient.patient_number}</Descriptions.Item>
      <Descriptions.Item label="Name">
        {[patient.first_name, patient.middle_name, patient.last_name].filter(Boolean).join(' ')}
      </Descriptions.Item>
      <Descriptions.Item label="Date of birth">{displayValue(patient.date_of_birth)}</Descriptions.Item>
      <Descriptions.Item label="Sex at birth">{displayValue(patient.sex_at_birth)}</Descriptions.Item>
      <Descriptions.Item label="Phone">{displayValue(patient.phone_number)}</Descriptions.Item>
      <Descriptions.Item label="Email">{displayValue(patient.email)}</Descriptions.Item>
      <Descriptions.Item label="Address">{displayValue(patient.address)}</Descriptions.Item>
      <Descriptions.Item label="Next of kin">
        {patient.next_of_kin_name
          ? `${patient.next_of_kin_name} · ${patient.next_of_kin_phone} · ${patientRelationship(patient)}`
          : '—'}
      </Descriptions.Item>
    </Descriptions>
  )
}

function ClinicalWorkflow({ mode, csrfToken, currentUserId }: ClinicalWorkflowProps) {
  const isNursing = mode === 'nursing'
  const [queue, setQueue] = useState<QueuePage>({ items: [], total: 0, limit: 50, offset: 0 })
  const [selectedVisit, setSelectedVisit] = useState<ClinicalVisit | null>(null)
  const [triageForm, setTriageForm] = useState<TriageForm>(EMPTY_TRIAGE)
  const [noteBody, setNoteBody] = useState('')
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null)
  const [activeDraftVersion, setActiveDraftVersion] = useState<number | null>(null)
  const [addendumTargetId, setAddendumTargetId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [queueOffset, setQueueOffset] = useState(0)
  const [showCompleted, setShowCompleted] = useState(false)

  const loadQueue = useCallback(async () => {
    try {
      const path = isNursing ? '/nursing/triage-queue' : '/doctors/consultation-queue'
      const params = new URLSearchParams({
        limit: '50',
        offset: String(queueOffset),
      })
      if (!isNursing && showCompleted) params.set('include_completed', 'true')
      const result = await apiRequest<QueuePage>(`${path}?${params.toString()}`)
      setError('')
      setQueue(result)
      setSelectedVisit((current) =>
        current ? result.items.find((visit) => visit.id === current.id) ?? current : current,
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load the queue.')
    } finally {
      setLoading(false)
    }
  }, [isNursing, queueOffset, showCompleted])

  useEffect(() => {
    void loadQueue()
  }, [loadQueue])

  useEffect(() => {
    const handleDataChanged = (event: Event) => {
      if (!(event instanceof CustomEvent)) return
      const changedEvents = event.detail as SystemEvent[]
      const categories = new Set(changedEvents.map((change) => change.category))
      const relevantCategories = isNursing
        ? ['patient_access', 'nursing']
        : ['patient_access', 'nursing', 'clinical']
      if (relevantCategories.some((category) => categories.has(category))) {
        void loadQueue()
      }
    }

    window.addEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
    window.addEventListener(SYSTEM_MANUAL_REFRESH_EVENT, loadQueue)
    return () => {
      window.removeEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
      window.removeEventListener(SYSTEM_MANUAL_REFRESH_EVENT, loadQueue)
    }
  }, [isNursing, loadQueue])

  const openVisit = (visit: ClinicalVisit) => {
    setSelectedVisit(visit)
    setError('')
    setSuccess('')
    setTriageForm(EMPTY_TRIAGE)
    setNoteBody('')
    setActiveDraftId(null)
    setActiveDraftVersion(null)
    setAddendumTargetId(null)
  }

  const closeVisit = () => {
    setSelectedVisit(null)
    setActiveDraftId(null)
    setActiveDraftVersion(null)
    setAddendumTargetId(null)
    setNoteBody('')
    setTriageForm(EMPTY_TRIAGE)
  }

  const submitTriage = async () => {
    if (!selectedVisit) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await apiRequest(`/nursing/visits/${selectedVisit.id}/triage`, {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          ...triageForm,
          notes: triageForm.notes.trim() || null,
        }),
      })
      setSuccess(`Triage recorded for ${selectedVisit.patient_number}.`)
      closeVisit()
      await loadQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save triage.')
    } finally {
      setSaving(false)
    }
  }

  const startConsultation = async () => {
    if (!selectedVisit) return
    setSaving(true)
    setError('')
    try {
      await apiRequest(`/doctors/visits/${selectedVisit.id}/start`, {
        method: 'POST',
        headers: requestHeaders(csrfToken),
      })
      setSelectedVisit((visit) =>
        visit ? { ...visit, workflow_state: 'consultation_in_progress' } : visit,
      )
      await loadQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to start consultation.')
    } finally {
      setSaving(false)
    }
  }

  const saveDraft = async () => {
    if (!selectedVisit || !noteBody.trim()) {
      setError('Enter the consultation note before saving.')
      return
    }
    if (activeDraftId && activeDraftVersion === null) {
      setError('Refresh the note before saving changes.')
      return
    }
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const savedNote = await apiRequest<ConsultationNote>(
        activeDraftId
          ? `/doctors/notes/${activeDraftId}`
          : addendumTargetId
            ? `/doctors/notes/${addendumTargetId}/addenda`
            : `/doctors/visits/${selectedVisit.id}/notes`,
        {
          method: activeDraftId ? 'PUT' : 'POST',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify({
            body: noteBody,
            ...(activeDraftId && activeDraftVersion !== null
              ? { version: activeDraftVersion }
              : {}),
          }),
        },
      )
      setActiveDraftId(savedNote.id)
      setActiveDraftVersion(savedNote.version)
      setAddendumTargetId(null)
      setNoteBody(savedNote.body)
      setSuccess(savedNote.note_type === 'addendum' ? 'Addendum draft saved.' : 'Draft saved.')
      await loadQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save the note.')
    } finally {
      setSaving(false)
    }
  }

  const signDraft = async () => {
    if (!activeDraftId || activeDraftVersion === null) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const activeNote = selectedVisit?.consultation_notes.find(
        (note) => note.id === activeDraftId,
      )
      if (!activeNote) {
        throw new Error('Draft no longer available. Refresh and try again.')
      }
      let version = activeDraftVersion
      if (activeNote.body !== noteBody.trim()) {
        const updatedNote = await apiRequest<ConsultationNote>(`/doctors/notes/${activeDraftId}`, {
          method: 'PUT',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify({ body: noteBody, version }),
        })
        version = updatedNote.version
        setActiveDraftVersion(version)
      }
      await apiRequest(`/doctors/notes/${activeDraftId}/sign`, {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ version }),
      })
      setActiveDraftId(null)
      setActiveDraftVersion(null)
      setNoteBody('')
      setSuccess('Note signed and locked.')
      await loadQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to sign the note.')
    } finally {
      setSaving(false)
    }
  }

  const completeVisit = async () => {
    if (!selectedVisit) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await apiRequest(`/doctors/visits/${selectedVisit.id}/complete`, {
        method: 'POST',
        headers: requestHeaders(csrfToken),
      })
      setSuccess(`Visit ${selectedVisit.visit_number} completed.`)
      closeVisit()
      await loadQueue()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to complete visit.')
    } finally {
      setSaving(false)
    }
  }

  const columns: TableColumnsType<ClinicalVisit> = [
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
    {
      title: 'ARRIVED',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string | null) => value ? new Date(value).toLocaleString() : '—',
    },
    {
      title: 'STATUS',
      dataIndex: 'workflow_state',
      key: 'workflow_state',
      render: (value: string) => <Tag color="gold">{value.replaceAll('_', ' ')}</Tag>,
    },
    {
      title: '',
      key: 'actions',
      align: 'right',
      render: (_, visit) => (
        <Button type="primary" onClick={() => openVisit(visit)}>
          {isNursing ? 'Record triage' : 'View / consult'}
        </Button>
      ),
    },
  ]

  const activeNote = selectedVisit?.consultation_notes.find((note) => note.id === activeDraftId)
  const hasSignedConsultation = selectedVisit?.consultation_notes.some(
    (note) => note.note_type === 'consultation' && note.status === 'signed',
  ) ?? false
  const hasUnsignedNotes = selectedVisit?.consultation_notes.some(
    (note) => note.status === 'draft',
  ) ?? false
  const canCompleteVisit = hasSignedConsultation && !hasUnsignedNotes

  return (
    <div className="patient-access">
      <div className="page-heading">
        <div>
          <Text className="eyebrow">{isNursing ? 'NURSING' : 'CLINICAL'}</Text>
          <Title level={3}>{isNursing ? 'Triage queue' : 'Consultation queue'}</Title>
          <Text type="secondary">
            {isNursing
              ? 'Review queued patients, their details and record triage observations.'
              : 'Review triaged patients, document consultations and complete visits.'}
          </Text>
        </div>
        <Space>
          {!isNursing && (
            <Space>
              <Text>Show completed</Text>
              <Switch
                checked={showCompleted}
                onChange={(checked) => {
                  setLoading(true)
                  setQueueOffset(0)
                  setShowCompleted(checked)
                }}
              />
            </Space>
          )}
          <Button
            onClick={() => {
              setLoading(true)
              void loadQueue()
            }}
            loading={loading}
          >
            Refresh queue
          </Button>
        </Space>
      </div>

      <Alert
        showIcon
        type="warning"
        title="Development workflow only. Use synthetic data; clinical forms and workflows require hospital approval before real patient data is used."
        className="admin-notice"
      />
      {error && <Alert showIcon type="error" title={error} className="admin-notice" />}
      {success && <Alert showIcon type="success" title={success} className="admin-notice" />}

      <Card size="small" title={isNursing ? 'Waiting for triage' : 'Waiting for consultation'}>
        <Table
          columns={columns}
          dataSource={queue.items}
          loading={loading}
          rowKey="id"
          pagination={{
            current: Math.floor(queue.offset / queue.limit) + 1,
            pageSize: queue.limit,
            total: queue.total,
            onChange: (page, pageSize) => {
              setLoading(true)
              setQueueOffset((page - 1) * pageSize)
            },
            showSizeChanger: false,
          }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Modal
        title={
          selectedVisit
            ? `${isNursing ? 'Triage' : 'Visit'}: ${selectedVisit.visit_number}`
            : undefined
        }
        open={selectedVisit !== null}
        onCancel={closeVisit}
        footer={null}
        width={760}
        destroyOnHidden
      >
        {selectedVisit && (
          <Space orientation="vertical" size={16} className="modal-full-width">
            {error && <Alert showIcon type="error" title={error} />}
            <PatientDetails patient={selectedVisit.patient} />
            <Text type="secondary">
              {selectedVisit.clinic} · {selectedVisit.visit_type} ·{' '}
              {selectedVisit.workflow_state.replaceAll('_', ' ')}
            </Text>

            {isNursing ? (
              <>
                <Divider titlePlacement="left">Triage observations</Divider>
                <div className="admin-form-grid">
                  {TRIAGE_FIELDS.map((field) => (
                    <label className="auth-field" key={field.name}>
                      <span>{field.label}</span>
                      <InputNumber
                        aria-label={field.label}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        value={triageForm[field.name]}
                        onChange={(value) =>
                          setTriageForm((form) => ({ ...form, [field.name]: value }))
                        }
                        className="modal-full-width"
                      />
                    </label>
                  ))}
                  <label className="auth-field">
                    <span>Nurse notes</span>
                    <Input.TextArea
                      aria-label="Nurse notes"
                      maxLength={2000}
                      rows={3}
                      value={triageForm.notes}
                      onChange={(event) =>
                        setTriageForm((form) => ({ ...form, notes: event.target.value }))
                      }
                    />
                  </label>
                </div>
                <Button type="primary" loading={saving} onClick={() => void submitTriage()}>
                  Submit triage to doctor
                </Button>
              </>
            ) : (
              <>
                {selectedVisit.triage && (
                  <>
                    <Divider titlePlacement="left">Nurse triage</Divider>
                    <Descriptions size="small" column={2} bordered>
                      <Descriptions.Item label="Blood pressure">
                        {selectedVisit.triage.blood_pressure_systolic === null
                          ? '—'
                          : `${selectedVisit.triage.blood_pressure_systolic}/
                            ${selectedVisit.triage.blood_pressure_diastolic} mmHg`}
                      </Descriptions.Item>
                      <Descriptions.Item label="Pulse">
                        {displayValue(selectedVisit.triage.pulse_rate_bpm)} bpm
                      </Descriptions.Item>
                      <Descriptions.Item label="Temperature">
                        {displayValue(selectedVisit.triage.temperature_celsius)} °C
                      </Descriptions.Item>
                      <Descriptions.Item label="Respiration">
                        {displayValue(selectedVisit.triage.respiratory_rate_bpm)} /min
                      </Descriptions.Item>
                      <Descriptions.Item label="Oxygen saturation">
                        {displayValue(selectedVisit.triage.oxygen_saturation_percent)}%
                      </Descriptions.Item>
                      <Descriptions.Item label="Weight">
                        {displayValue(selectedVisit.triage.weight_kg)} kg
                      </Descriptions.Item>
                      <Descriptions.Item label="Height">
                        {displayValue(selectedVisit.triage.height_cm)} cm
                      </Descriptions.Item>
                      <Descriptions.Item label="Pain score">
                        {displayValue(selectedVisit.triage.pain_score)}
                      </Descriptions.Item>
                      <Descriptions.Item label="Nurse notes" span={2}>
                        {displayValue(selectedVisit.triage.notes)}
                      </Descriptions.Item>
                    </Descriptions>
                  </>
                )}

                {selectedVisit.workflow_state === 'awaiting_doctor' && (
                  <Button
                    type="primary"
                    loading={saving}
                    onClick={() => void startConsultation()}
                  >
                    Start consultation
                  </Button>
                )}

                {selectedVisit.consultation_notes.length > 0 && (
                  <>
                    <Divider titlePlacement="left">Consultation notes</Divider>
                    <Space orientation="vertical" className="modal-full-width">
                      {selectedVisit.consultation_notes.map((note) => (
                        <Card
                          key={note.id}
                          size="small"
                          title={
                            <Space>
                              <Tag color={note.status === 'signed' ? 'green' : 'gold'}>
                                {note.status}
                              </Tag>
                              <Text>{note.note_type}</Text>
                            </Space>
                          }
                          extra={note.status === 'draft' && note.author_user_id === currentUserId ? (
                            <Button
                              size="small"
                              onClick={() => {
                                setActiveDraftId(note.id)
                                setActiveDraftVersion(note.version)
                                setAddendumTargetId(null)
                                setNoteBody(note.body)
                              }}
                            >
                              Edit draft
                            </Button>
                          ) : note.status === 'signed' ? (
                            <Button
                              size="small"
                              onClick={() => {
                                setActiveDraftId(null)
                                setActiveDraftVersion(null)
                                setAddendumTargetId(note.id)
                                setNoteBody('')
                              }}
                            >
                              Add addendum
                            </Button>
                          ) : null}
                        >
                          <Text>{note.body}</Text>
                          <br />
                          <Text type="secondary">
                            {note.signed_at
                              ? `Signed ${new Date(note.signed_at).toLocaleString()}`
                              : `Saved ${note.created_at ? new Date(note.created_at).toLocaleString() : ''}`}
                          </Text>
                        </Card>
                      ))}
                    </Space>
                  </>
                )}

                {(selectedVisit.workflow_state === 'consultation_in_progress' ||
                  (selectedVisit.workflow_state === 'completed' &&
                    (addendumTargetId !== null || activeNote?.note_type === 'addendum'))) && (
                  <>
                    <Divider titlePlacement="left">
                      {addendumTargetId || activeNote?.note_type === 'addendum'
                        ? 'Addendum draft'
                        : 'Consultation note draft'}
                    </Divider>
                    <Input.TextArea
                      aria-label="Consultation note"
                      rows={6}
                      maxLength={20000}
                      value={noteBody}
                      onChange={(event) => setNoteBody(event.target.value)}
                      placeholder="Write the consultation note..."
                    />
                    <Space>
                      <Button loading={saving} onClick={() => void saveDraft()}>
                        Save draft
                      </Button>
                      {activeDraftId && activeNote?.author_user_id === currentUserId && (
                        <Button
                          type="primary"
                          loading={saving}
                          onClick={() => void signDraft()}
                        >
                          Sign and lock
                        </Button>
                      )}
                      {selectedVisit.workflow_state === 'consultation_in_progress' &&
                        canCompleteVisit && (
                        <Button
                          type="primary"
                          loading={saving}
                          onClick={() => void completeVisit()}
                        >
                          Complete visit
                        </Button>
                      )}
                    </Space>
                  </>
                )}

                {selectedVisit.workflow_state === 'completed' && (
                  <Text type="secondary">
                    This visit is complete. Signed notes remain locked; use an addendum for corrections.
                  </Text>
                )}
              </>
            )}
          </Space>
        )}
      </Modal>
    </div>
  )
}

export default ClinicalWorkflow
