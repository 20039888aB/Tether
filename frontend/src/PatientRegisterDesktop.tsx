import { useEffect, useRef, useState } from 'react'
import {
  apiRequest,
  SYSTEM_DATA_CHANGED_EVENT,
} from './api'
import './PatientRegisterDesktop.css'

type PatientForm = {
  first_name: string
  last_name: string
  middle_name: string
  date_of_birth: string
  sex_at_birth: string
  nationality: string
  document_type: string
  document_number: string
  marital_status: string
  category: string
  phone_country_code: string
  phone_number: string
  city_town: string
  sub_county_estate: string
  email: string
  address: string
  postal_code: string
  next_of_kin_name: string
  next_of_kin_phone_country_code: string
  next_of_kin_phone: string
  next_of_kin_email: string
  next_of_kin_relationship: string
  next_of_kin_relationship_other: string
  next_of_kin_id_number: string
  debtor_account: string
  staff_account: string
  operating_currency: string
  department: string
  legacy_number: string
  tax_pin: string
}

type PatientRecord = {
  id: string
  patient_number: string
  version: number
  first_name: string
  middle_name: string | null
  last_name: string
  date_of_birth: string | null
  sex_at_birth: string | null
  nationality: string | null
  document_type: string | null
  document_number: string | null
  marital_status: string | null
  category: string | null
  phone_country_code: string
  phone_number: string | null
  city_town: string | null
  sub_county_estate: string | null
  email: string | null
  address: string | null
  postal_code: string | null
  next_of_kin_name: string | null
  next_of_kin_phone_country_code: string
  next_of_kin_phone: string | null
  next_of_kin_email: string | null
  next_of_kin_relationship: string | null
  next_of_kin_relationship_other: string | null
  next_of_kin_id_number: string | null
  debtor_account: string | null
  staff_account: string | null
  operating_currency: string
  department: string | null
  legacy_number: string | null
  tax_pin: string | null
}

type VisitType = { id: number; name: string; color_hex: string }
type Clinic = { id: number; code: string; name: string; visit_types: VisitType[] }
type VisitRecord = { visit_number: string }
type RowPosition = 'r1' | 'r2' | 'r3' | 'r4'
type ColumnPosition = 'c1' | 'c2' | 'c3'
type FormField = keyof PatientForm

type Props = {
  csrfToken: string
  username: string
  canSearchPatients: boolean
  canCreatePatient: boolean
  canEditPatient: boolean
  canOpenVisit: boolean
  onNavigate: (key: string) => void
}

const EMPTY_FORM: PatientForm = {
  first_name: '',
  last_name: '',
  middle_name: '',
  date_of_birth: '',
  sex_at_birth: '',
  nationality: 'Kenya',
  document_type: '',
  document_number: '',
  marital_status: '',
  category: '',
  phone_country_code: '+254',
  phone_number: '',
  city_town: '',
  sub_county_estate: '',
  email: '',
  address: '',
  postal_code: '',
  next_of_kin_name: '',
  next_of_kin_phone_country_code: '+254',
  next_of_kin_phone: '',
  next_of_kin_email: '',
  next_of_kin_relationship: '',
  next_of_kin_relationship_other: '',
  next_of_kin_id_number: '',
  debtor_account: '',
  staff_account: '',
  operating_currency: 'KES',
  department: '',
  legacy_number: 'None',
  tax_pin: '',
}

const RELATIONSHIPS = [
  ['Brother', 'brother'],
  ['Sister', 'sister'],
  ['Parent', 'parent'],
  ['Spouse', 'spouse'],
  ['Child', 'child'],
  ['Friend', 'friend'],
  ['Other', 'other'],
]

const COUNTRY_CODES = [
  ['🇰🇪 254', '+254'],
  ['🇺🇬 256', '+256'],
  ['🇹🇿 255', '+255'],
  ['🇷🇼 250', '+250'],
  ['🇸🇴 252', '+252'],
  ['🇪🇹 251', '+251'],
]

function requestHeaders(csrfToken: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }
}

function formatBirthDate(value: string) {
  if (!value) return ''
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  const day = date.getDate()
  const suffix = day % 10 === 1 && day !== 11
    ? 'st'
    : day % 10 === 2 && day !== 12
      ? 'nd'
      : day % 10 === 3 && day !== 13
        ? 'rd'
        : 'th'
  const weekday = date.toLocaleDateString('en-GB', { weekday: 'short' })
  const month = date.toLocaleDateString('en-GB', { month: 'short' })
  return `${weekday}, ${day}${suffix} ${month} ${date.getFullYear()}`
}

function patientFormFromRecord(patient: PatientRecord): PatientForm {
  return {
    first_name: patient.first_name,
    last_name: patient.last_name,
    middle_name: patient.middle_name ?? '',
    date_of_birth: patient.date_of_birth ?? '',
    sex_at_birth: patient.sex_at_birth ?? '',
    nationality: patient.nationality ?? '',
    document_type: patient.document_type ?? '',
    document_number: patient.document_number ?? '',
    marital_status: patient.marital_status ?? '',
    category: patient.category ?? '',
    phone_country_code: patient.phone_country_code || '+254',
    phone_number: patient.phone_number?.replace(/^\+\d{1,4}/, '') ?? '',
    city_town: patient.city_town ?? '',
    sub_county_estate: patient.sub_county_estate ?? '',
    email: patient.email ?? '',
    address: patient.address ?? '',
    postal_code: patient.postal_code ?? '',
    next_of_kin_name: patient.next_of_kin_name ?? '',
    next_of_kin_phone_country_code: patient.next_of_kin_phone_country_code || '+254',
    next_of_kin_phone:
      patient.next_of_kin_phone?.replace(/^\+\d{1,4}/, '') ?? '',
    next_of_kin_email: patient.next_of_kin_email ?? '',
    next_of_kin_relationship: patient.next_of_kin_relationship ?? '',
    next_of_kin_relationship_other: patient.next_of_kin_relationship_other ?? '',
    next_of_kin_id_number: patient.next_of_kin_id_number ?? '',
    debtor_account: patient.debtor_account ?? '',
    staff_account: patient.staff_account ?? '',
    operating_currency: patient.operating_currency || 'KES',
    department: patient.department ?? '',
    legacy_number: patient.legacy_number ?? 'None',
    tax_pin: patient.tax_pin ?? '',
  }
}

function inlineIcon(kind: string) {
  const paths: Record<string, string> = {
    merge: 'M6 4v5a3 3 0 0 0 3 3h6m-4-4 4 4-4 4M18 4v5a3 3 0 0 1-3 3',
    imaging: 'M4 5h16v14H4zM7 16l3-4 2 2 2-3 3 5M8 9h.01',
    lab: 'M9 3h6m-5 0v6l-5 9h14l-5-9V3M7 15h10',
    procedure: 'M5 19 19 5M7 5l12 12M4 8l4-4m8 16 4-4',
    family: 'M8 7a3 3 0 1 0 0-6 3 3 0 0 0 0 6m8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6M2 19c0-4 2-6 6-6s6 2 6 6m-2-5c1-1 2-1 4-1 4 0 6 2 6 6',
    care: 'M12 21s-8-4.5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6.5-8 11-8 11m-4-9h8m-4-4v8',
    print: 'M6 8V3h12v5M6 17H4V9h16v8h-2M6 13h12v8H6z',
    search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6',
    queue: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8m-8 9c0-4 3-6 8-6s8 2 8 6m-4-9h8m-4-4v8',
    calendar: 'M4 5h16v16H4zM8 3v4m8-4v4M4 10h16',
    clear: 'm6 6 12 12M18 6 6 18',
    check: 'm5 12 4 4L19 6',
    close: 'm6 6 12 12M18 6 6 18',
    start: 'M8 4v16l12-8z',
    bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4',
    people: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6m8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6M2 20c0-3 2-5 6-5s6 2 6 5m0-5c4 0 6 2 6 5',
    add: 'M12 5v14m-7-7h14',
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[kind] ?? paths.search} />
    </svg>
  )
}

function PatientRegisterDesktop({
  csrfToken,
  username,
  canSearchPatients,
  canCreatePatient,
  canEditPatient,
  canOpenVisit,
  onNavigate,
}: Props) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [invalidFields, setInvalidFields] = useState<Set<FormField>>(new Set())
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [patientNumber, setPatientNumber] = useState('11314')
  const [visitNumber, setVisitNumber] = useState('')
  const [patient, setPatient] = useState<PatientRecord | null>(null)
  const [photoUrl, setPhotoUrl] = useState('')
  const [activeTab, setActiveTab] = useState('Patient Information')
  const [expandedGroups, setExpandedGroups] = useState(
    new Set(['Manage Patients', 'Calendar']),
  )
  const [clinics, setClinics] = useState<Clinic[]>([])
  const [selectedClinicId, setSelectedClinicId] = useState<number | null>(null)
  const [selectedVisitTypeId, setSelectedVisitTypeId] = useState<number | null>(null)
  const [queueDialogOpen, setQueueDialogOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const [searchResults, setSearchResults] = useState<PatientRecord[]>([])
  const [photoError, setPhotoError] = useState('')
  const dateInputRef = useRef<HTMLInputElement>(null)
  const photoInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!canCreatePatient) return
    void apiRequest<{ patient_number: string }>('/patients/next-number')
      .then((result) => setPatientNumber(result.patient_number.replace(/^TTH-/, '')))
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : 'Unable to load the next patient number.')
      })
  }, [canCreatePatient])

  useEffect(() => {
    if (!canOpenVisit) return
    void apiRequest<{ items: Clinic[] }>('/clinics/available')
      .then((result) => setClinics(result.items))
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : 'Unable to load available clinics.')
      })
  }, [canOpenVisit])

  useEffect(() => {
    if (photoUrl) return () => URL.revokeObjectURL(photoUrl)
  }, [photoUrl])

  const updateForm = (name: FormField, value: string) => {
    setForm((current) => ({ ...current, [name]: value }))
    setInvalidFields((current) => {
      if (!current.has(name)) return current
      const next = new Set(current)
      next.delete(name)
      return next
    })
  }

  const phoneField = (
    label: string,
    col: ColumnPosition,
    row: RowPosition,
    name: 'phone_number' | 'next_of_kin_phone',
    codeName: 'phone_country_code' | 'next_of_kin_phone_country_code',
    required = false,
  ) => (
    <div className={`register-row ${col} ${row}`}>
      <label className={required ? 'required' : ''} htmlFor={name}>{label}:</label>
      <div className={`register-control phone-control${invalidFields.has(name) ? ' invalid' : ''}`}>
        <select
          aria-label={`${label} country code`}
          value={form[codeName]}
          onChange={(event) => updateForm(codeName, event.target.value)}
        >
          {COUNTRY_CODES.map(([country, value]) => (
            <option value={value} key={value}>{country}</option>
          ))}
        </select>
        <input
          id={name}
          inputMode="numeric"
          value={form[name]}
          onChange={(event) =>
            updateForm(name, event.target.value.replace(/\D/g, '').slice(0, 15))
          }
          aria-invalid={invalidFields.has(name)}
        />
      </div>
    </div>
  )

  const textField = (
    label: string,
    name: FormField,
    col: ColumnPosition,
    row: RowPosition,
    required = false,
    placeholder = '',
  ) => (
    <div className={`register-row ${col} ${row}`}>
      <label className={required ? 'required' : ''} htmlFor={name}>{label}:</label>
      <input
        id={name}
        className={`register-control${invalidFields.has(name) ? ' invalid' : ''}`}
        value={form[name]}
        placeholder={placeholder}
        onChange={(event) => updateForm(name, event.target.value)}
        aria-invalid={invalidFields.has(name)}
      />
    </div>
  )

  const selectField = (
    label: string,
    name: FormField,
    col: ColumnPosition,
    row: RowPosition,
    options: Array<[string, string]>,
    placeholder = '',
  ) => (
    <div className={`register-row ${col} ${row}`}>
      <label htmlFor={name}>{label}:</label>
      <select
        id={name}
        className={`register-control register-select${invalidFields.has(name) ? ' invalid' : ''}`}
        value={form[name]}
        onChange={(event) => updateForm(name, event.target.value)}
        aria-invalid={invalidFields.has(name)}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map(([labelValue, value]) => (
          <option value={value} key={value}>{labelValue}</option>
        ))}
      </select>
    </div>
  )

  const validate = () => {
    const required: FormField[] = [
      'first_name',
      'last_name',
      'date_of_birth',
      'sex_at_birth',
      'nationality',
      'phone_number',
      'next_of_kin_name',
      'next_of_kin_phone',
      'next_of_kin_relationship',
    ]
    const missing = new Set(required.filter((field) => !form[field].trim()))
    setInvalidFields(missing)
    if (missing.size > 0) {
      setError('Complete the required patient and next-of-kin details before submitting.')
      return false
    }
    if (form.next_of_kin_relationship === 'other' && !form.next_of_kin_relationship_other.trim()) {
      setInvalidFields(new Set(['next_of_kin_relationship_other']))
      setError('Specify the next-of-kin relationship when Other is selected.')
      return false
    }
    if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setInvalidFields(new Set(['email']))
      setError('Enter a valid patient email address.')
      return false
    }
    if (
      form.next_of_kin_email.trim() &&
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.next_of_kin_email.trim())
    ) {
      setInvalidFields(new Set(['next_of_kin_email']))
      setError('Enter a valid next-of-kin email address.')
      return false
    }
    return true
  }

  const patientPayload = () => ({
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    middle_name: form.middle_name.trim() || null,
    date_of_birth: form.date_of_birth,
    sex_at_birth: form.sex_at_birth,
    nationality: form.nationality,
    document_type: form.document_type || null,
    document_number: form.document_number.trim() || null,
    marital_status: form.marital_status || null,
    category: form.category || null,
    phone_country_code: form.phone_country_code,
    phone_number: `${form.phone_country_code}${form.phone_number.replace(/^0/, '')}`,
    city_town: form.city_town || null,
    sub_county_estate: form.sub_county_estate.trim() || null,
    email: form.email.trim() || null,
    address: form.address.trim() || null,
    postal_code: form.postal_code.trim() || null,
    next_of_kin_name: form.next_of_kin_name.trim(),
    next_of_kin_phone_country_code: form.next_of_kin_phone_country_code,
    next_of_kin_phone:
      `${form.next_of_kin_phone_country_code}${form.next_of_kin_phone.replace(/^0/, '')}`,
    next_of_kin_email: form.next_of_kin_email.trim() || null,
    next_of_kin_relationship: form.next_of_kin_relationship,
    next_of_kin_relationship_other:
      form.next_of_kin_relationship === 'other'
        ? form.next_of_kin_relationship_other.trim() || null
        : null,
    next_of_kin_id_number: form.next_of_kin_id_number.trim() || null,
    debtor_account: form.debtor_account.trim() || null,
    staff_account: form.staff_account.trim() || null,
    operating_currency: form.operating_currency,
    department: form.department.trim() || null,
    legacy_number: form.legacy_number.trim() || null,
    tax_pin: form.tax_pin.trim() || null,
  })

  const submitPatient = async () => {
    setError('')
    setNotice('')
    if (!canCreatePatient && !patient) {
      setError('Your account does not have permission to register patients.')
      return
    }
    if (!validate()) return
    setSaving(true)
    try {
      const result = await apiRequest<PatientRecord>(
        patient ? `/patients/${patient.id}` : '/patients',
        {
          method: patient ? 'PUT' : 'POST',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify({
            ...patientPayload(),
            ...(patient ? { version: patient.version } : {}),
          }),
        },
      )
      setPatient(result)
      setPatientNumber(result.patient_number.replace(/^TTH-/, ''))
      setNotice(
        patient
          ? `Patient ${result.patient_number} updated.`
          : `Patient registered. TETHER number: ${result.patient_number}.`,
      )
      window.dispatchEvent(
        new CustomEvent(SYSTEM_DATA_CHANGED_EVENT, {
          detail: [{ category: 'patient_access', action: 'patient.registration.create' }],
        }),
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save the patient record.')
    } finally {
      setSaving(false)
    }
  }

  const openQueueDialog = () => {
    setError('')
    setNotice('')
    if (!canOpenVisit) {
      setError('Your account does not have permission to add a patient to the OPD queue.')
      return
    }
    if (!patient) {
      setError('Save the patient record before adding the patient to a queue.')
      return
    }
    setQueueDialogOpen(true)
  }

  const addToQueue = async () => {
    const selectedClinic = clinics.find((clinic) => clinic.id === selectedClinicId)
    const selectedVisitType = selectedClinic?.visit_types.find(
      (visitType) => visitType.id === selectedVisitTypeId,
    )
    if (!patient || !selectedClinic || !selectedVisitType) {
      setError('Select an available clinic and visit type.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const visit = await apiRequest<VisitRecord>('/outpatient-visits', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          patient_id: patient.id,
          clinic_id: selectedClinic.id,
          visit_type_id: selectedVisitType.id,
          clinic: selectedClinic.name,
          visit_type: selectedVisitType.name,
        }),
      })
      setVisitNumber(visit.visit_number)
      setQueueDialogOpen(false)
      setNotice(`${patient.patient_number} added to ${selectedClinic.name}.`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to add patient to queue.')
    } finally {
      setSaving(false)
    }
  }

  const resetForm = () => {
    setForm(EMPTY_FORM)
    setInvalidFields(new Set())
    setPatient(null)
    setPatientNumber('11314')
    setVisitNumber('')
    setPhotoUrl('')
    setPhotoError('')
    setError('')
    setNotice('')
  }

  const runSearch = async () => {
    if (!canSearchPatients || !searchValue.trim()) return
    setError('')
    try {
      const page = await apiRequest<{ items: PatientRecord[] }>(
        `/patients?q=${encodeURIComponent(searchValue.trim())}&limit=20`,
      )
      setSearchResults(page.items)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to search the registry.')
    }
  }

  const selectPatient = (record: PatientRecord) => {
    if (!canEditPatient) {
      setError('Your account can search the registry but cannot edit patient records.')
      return
    }
    setPatient(record)
    setForm(patientFormFromRecord(record))
    setPatientNumber(record.patient_number.replace(/^TTH-/, ''))
    setVisitNumber('')
    setSearchOpen(false)
    setNotice(`Loaded ${record.patient_number} for editing.`)
    setInvalidFields(new Set())
  }

  const group = (
    title: string,
    items: Array<[string, string, string]>,
  ) => (
    <div className="tree-group" key={title}>
      <button
        className="tree-group-title"
        type="button"
        onClick={() =>
          setExpandedGroups((current) => {
            const next = new Set(current)
            if (next.has(title)) next.delete(title)
            else next.add(title)
            return next
          })
        }
      >
        <span className="tree-toggle">{expandedGroups.has(title) ? '⊟' : '⊞'}</span>
        {title}
      </button>
      {expandedGroups.has(title) && items.map(([label, key, icon]) => (
        <button
          className={`tree-item${key === 'patient-register' ? ' selected' : ''}`}
          key={key}
          type="button"
          onClick={() => key !== 'patient-register' && onNavigate(key)}
        >
          <span className="tree-grid-icon">{icon}</span>
          {label}
        </button>
      ))}
    </div>
  )

  const toolbar = [
    ['Merge Other Patients', 'blue', 'merge'],
    ['Imaging Exam', 'lav', 'imaging'],
    ['Laboratory Investigation', 'mag', 'lab'],
    ['Minor Procedure', 'teal', 'procedure'],
    ['Family Health', 'orange', 'family'],
    ['Ancillary Care', 'green', 'care'],
    ['Print Details', 'grey', 'print'],
    ['Registry Search', 'slate', 'search'],
  ]

  return (
    <div className="patient-register-window">
      <div className="register-titlebar">
        <span className="register-logo">+</span>
        <strong>Patient Management</strong>
        <div className="window-controls"><span>−</span><span>□</span><span>×</span></div>
      </div>

      <aside className="register-sidebar">
        {group('Manage Patients', [
          ['Patient Register', 'patient-register', '▦'],
          ['Patient Queue', 'patient-queue', '▦'],
          ['Admissions', 'admissions', '▦'],
        ])}
        {group('Calendar', [
          ['Appointments', 'appointments', '▦'],
          ['Reminders', 'reminders', '▦'],
          ['Clinic Planner', 'clinic-planner', '▦'],
        ])}
        {group('Configuration', [
          ['Clinics', 'clinics', '▦'],
          ['Administration', 'settings', '▦'],
        ])}
        {group('Reports', [['Patient Reports', 'reports', '▦']])}
        {group('Enquiries', [['Patient Enquiries', 'enquiries', '▦']])}
      </aside>

      <div className="register-toolbar">
        <div className="toolbar-shortcuts">
          {toolbar.map(([label, color, icon]) => (
            <button
              type="button"
              className="toolbar-shortcut"
              key={label}
              onClick={() => {
                if (label === 'Registry Search') setSearchOpen(true)
                if (label === 'Print Details') window.print()
              }}
            >
              <span className={`toolbar-icon ${color}`}>{inlineIcon(icon)}</span>
              <span>{label}</span>
            </button>
          ))}
        </div>
        <div className="toolbar-identifiers">
          <label>Patient<br />Number</label>
          <strong className="number-badge">{patientNumber}</strong>
          <label>Visit<br />Number</label>
          <strong className="visit-badge">{visitNumber.replace(/^OPD-/, '')}</strong>
          <button type="button" className="queue-button" onClick={openQueueDialog}>
            <span>{inlineIcon('queue')}<i>{inlineIcon('add')}</i></span>
            <b>Add To<br />Queue</b>
          </button>
        </div>
      </div>

      <div className="register-tabs" role="tablist">
        {[
          'Patient Information',
          'Medical Cover',
          'Emergency Contact',
          'Relationships',
          'Other Information',
        ].map((tab) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={`register-tab${activeTab === tab ? ' active' : ''}`}
            onClick={() => setActiveTab(tab)}
            key={tab}
          >
            {tab}
          </button>
        ))}
      </div>

      <main className="register-panel">
        {activeTab === 'Patient Information' ? (
          <>
            <fieldset className="register-section section-bio">
              <legend>Patient Biographical Data</legend>
              {textField('First Name', 'first_name', 'c1', 'r1', true)}
              {textField('Surname', 'last_name', 'c2', 'r1', true)}
              {textField('Other Name', 'middle_name', 'c3', 'r1')}
              <div className="register-row c1 r2">
                <label className="required" htmlFor="date_of_birth">Birth Date:</label>
                <div className={`register-control date-control${invalidFields.has('date_of_birth') ? ' invalid' : ''}`}>
                  <input
                    id="date_of_birth"
                    className="date-display"
                    readOnly
                    value={formatBirthDate(form.date_of_birth)}
                    aria-label="Birth date"
                    aria-invalid={invalidFields.has('date_of_birth')}
                  />
                  <button
                    type="button"
                    className="date-icon"
                    aria-label="Choose birth date"
                    onClick={() => dateInputRef.current?.showPicker()}
                  >
                    {inlineIcon('calendar')}
                  </button>
                  <button
                    type="button"
                    className="date-clear"
                    aria-label="Clear birth date"
                    onClick={() => updateForm('date_of_birth', '')}
                  >
                    {inlineIcon('clear')}
                  </button>
                  <input
                    ref={dateInputRef}
                    className="native-date-input"
                    type="date"
                    value={form.date_of_birth}
                    onChange={(event) => updateForm('date_of_birth', event.target.value)}
                  />
                </div>
              </div>
              {selectField('Gender', 'sex_at_birth', 'c2', 'r2', [
                ['Male', 'male'],
                ['Female', 'female'],
              ], 'Please select')}
              {selectField('Nationality', 'nationality', 'c3', 'r2', [
                ['Kenya', 'Kenya'],
                ['Uganda', 'Uganda'],
                ['Tanzania', 'Tanzania'],
                ['Rwanda', 'Rwanda'],
                ['Somalia', 'Somalia'],
                ['Ethiopia', 'Ethiopia'],
                ['Other', 'Other'],
              ])}
              {selectField('Document Type', 'document_type', 'c1', 'r3', [
                ['National ID', 'National ID'],
                ['Passport', 'Passport'],
                ['Birth Certificate', 'Birth Certificate'],
                ['Other', 'Other'],
              ], 'Please select')}
              {textField('Document No.', 'document_number', 'c2', 'r3')}
              {selectField('Marital Status', 'marital_status', 'c3', 'r3', [
                ['Single', 'Single'],
                ['Married', 'Married'],
                ['Separated', 'Separated'],
                ['Divorced', 'Divorced'],
                ['Widowed', 'Widowed'],
              ], 'Please select')}
              {selectField('Category', 'category', 'c1', 'r4', [
                ['Outpatient', 'Outpatient'],
                ['Inpatient', 'Inpatient'],
                ['Staff', 'Staff'],
                ['Child', 'Child'],
                ['Other', 'Other'],
              ], 'Please select a category')}
            </fieldset>

            <fieldset className="register-section section-contact">
              <legend>Patient Contact Information</legend>
              {phoneField('Phone', 'c1', 'r1', 'phone_number', 'phone_country_code', true)}
              {selectField('City/Town', 'city_town', 'c2', 'r1', [
                ['Chuka', 'CHUKA'],
                ['Nairobi', 'NAIROBI'],
                ['Meru', 'MERU'],
                ['Embu', 'EMBU'],
                ['Thika', 'THIKA'],
                ['Other', 'OTHER'],
              ])}
              {textField('Sub-County/Estate', 'sub_county_estate', 'c3', 'r1')}
              {textField('Email', 'email', 'c1', 'r2')}
              {textField('Postal Address', 'address', 'c2', 'r2')}
              {textField('Postal Code', 'postal_code', 'c3', 'r2')}
            </fieldset>

            <fieldset className="register-section section-next-of-kin">
              <legend>Emergency Contact/ Next of Kin Information</legend>
              {textField('Name', 'next_of_kin_name', 'c1', 'r1', true)}
              {phoneField('Phone', 'c2', 'r1', 'next_of_kin_phone', 'next_of_kin_phone_country_code', true)}
              {textField('Email', 'next_of_kin_email', 'c3', 'r1')}
              {selectField('Relationship', 'next_of_kin_relationship', 'c1', 'r2',
                RELATIONSHIPS, 'Please select')}
              {textField('ID/Passport No.', 'next_of_kin_id_number', 'c2', 'r2')}
            </fieldset>

            <fieldset className="register-section section-account">
              <legend>Account</legend>
              {textField(
                'Debtor Account',
                'debtor_account',
                'c1',
                'r1',
                false,
                'Select debtor tracking account if applicable',
              )}
              {textField(
                'Staff Account',
                'staff_account',
                'c2',
                'r1',
                false,
                'Link staff account if applicable',
              )}
              {selectField('Operating Currency', 'operating_currency', 'c3', 'r1', [
                ['Kenyan Shilling', 'KES'],
                ['US Dollar', 'USD'],
                ['Euro', 'EUR'],
                ['Pound Sterling', 'GBP'],
              ])}
              {textField(
                'Department',
                'department',
                'c1',
                'r2',
                false,
                'Select department if applicable',
              )}
              {textField('Legacy Number', 'legacy_number', 'c2', 'r2')}
              {textField('Tax PIN', 'tax_pin', 'c3', 'r2')}
            </fieldset>

            <div className="patient-photo">
              {photoUrl ? (
                <img src={photoUrl} alt="Patient preview" />
              ) : (
                <>
                  <svg viewBox="0 0 137 136" aria-hidden="true">
                    <circle cx="68" cy="36" r="26" fill="#aeb8cc" />
                    <path d="M17 128c2-29 17-44 51-44s49 15 52 44z" fill="#aeb8cc" />
                    <path d="m51 82 17 20 18-20 11 8-11 38H51L40 90z" fill="#fff" />
                  </svg>
                  <span>No Photo</span>
                </>
              )}
            </div>
            <button
              type="button"
              className="select-photo"
              onClick={() => photoInputRef.current?.click()}
            >
              <span>{inlineIcon('add')}</span> Select Photo
            </button>
            <input
              ref={photoInputRef}
              className="hidden-file"
              type="file"
              accept="image/*"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (!file) return
                if (!file.type.startsWith('image/')) {
                  setPhotoError('Choose an image file.')
                  return
                }
                setPhotoError('')
                setPhotoUrl(URL.createObjectURL(file))
              }}
            />
            {photoError && <span className="photo-error">{photoError}</span>}
          </>
        ) : (
          <div className="empty-register-tab" aria-label={`${activeTab} panel`} />
        )}

        {(error || notice) && (
          <div className={`register-feedback${error ? ' error' : ' success'}`} role="status">
            {error || notice}
            <button type="button" onClick={() => { setError(''); setNotice('') }}>×</button>
          </div>
        )}
        {saving && <div className="saving-indicator">Saving…</div>}

        {queueDialogOpen && (
          <div className="register-dialog-backdrop">
            <section className="register-dialog" role="dialog" aria-modal="true" aria-labelledby="queue-dialog-title">
              <header id="queue-dialog-title">Add Patient To Queue</header>
              <label>
                Clinic
                <select
                  value={selectedClinicId ?? ''}
                  onChange={(event) => {
                    const clinicId = event.target.value ? Number(event.target.value) : null
                    const clinic = clinics.find((entry) => entry.id === clinicId)
                    setSelectedClinicId(clinicId)
                    setSelectedVisitTypeId(clinic?.visit_types[0]?.id ?? null)
                  }}
                >
                  <option value="">Select clinic</option>
                  {clinics.map((clinic) => (
                    <option value={clinic.id} key={clinic.id}>{clinic.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Visit Type
                <select
                  value={selectedVisitTypeId ?? ''}
                  onChange={(event) =>
                    setSelectedVisitTypeId(event.target.value ? Number(event.target.value) : null)
                  }
                  disabled={!selectedClinicId}
                >
                  <option value="">Select visit type</option>
                  {clinics
                    .find((clinic) => clinic.id === selectedClinicId)
                    ?.visit_types.map((visitType) => (
                      <option value={visitType.id} key={visitType.id}>{visitType.name}</option>
                    ))}
                </select>
              </label>
              <footer>
                <button type="button" onClick={() => setQueueDialogOpen(false)}>Cancel</button>
                <button type="button" className="primary" onClick={() => void addToQueue()} disabled={saving}>
                  Add To Queue
                </button>
              </footer>
            </section>
          </div>
        )}

        {searchOpen && (
          <div className="register-dialog-backdrop">
            <section className="register-dialog registry-dialog" role="dialog" aria-modal="true" aria-labelledby="registry-dialog-title">
              <header id="registry-dialog-title">Registry Search</header>
              <div className="registry-search-row">
                <input
                  autoFocus
                  aria-label="Search patients"
                  placeholder="Name, patient number or phone"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void runSearch()
                  }}
                />
                <button type="button" onClick={() => void runSearch()}>Search</button>
              </div>
              <div className="registry-results">
                {searchResults.map((result) => (
                  <button type="button" key={result.id} onClick={() => selectPatient(result)}>
                    <strong>{result.patient_number}</strong>
                    <span>{result.first_name} {result.middle_name ?? ''} {result.last_name}</span>
                  </button>
                ))}
                {searchResults.length === 0 && <span>No matching records loaded.</span>}
              </div>
              <footer><button type="button" onClick={() => setSearchOpen(false)}>Close</button></footer>
            </section>
          </div>
        )}

        <div className="register-footer">
          <button type="button" onClick={() => void submitPatient()} disabled={saving || (!canCreatePatient && !patient)}>
            <span className="footer-icon ok">{inlineIcon('check')}</span>
            Submit
          </button>
          <span className="footer-divider" />
          <button type="button" onClick={resetForm}>
            <span className="footer-icon cancel">{inlineIcon('close')}</span>
            Close
          </button>
        </div>
      </main>

      <footer className="register-taskbar">
        <button className="start-button" type="button">{inlineIcon('start')}Start</button>
        <button type="button" onClick={() => onNavigate('wards')}>Ward Management</button>
        <button type="button" onClick={() => onNavigate('billing')}>Payment</button>
        <button className="task-active" type="button" onClick={() => onNavigate('patient-register')}>
          <span>+</span> Patient Manag…
        </button>
        <div className="taskbar-system">
          <span>{inlineIcon('people')}</span>
          <span className="taskbar-bell">{inlineIcon('bell')}<b>40</b></span>
          <strong>{username}</strong>
        </div>
      </footer>
    </div>
  )
}

export default PatientRegisterDesktop
