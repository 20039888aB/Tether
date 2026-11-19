import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
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

type Facility = { id: number; name: string }
type VisitType = { id: number; name: string; color_hex: string; is_active?: boolean }
type ClinicDoctor = { id: string; username: string; is_active: boolean }
type ClinicRow = {
  id: number
  code: string
  name: string
  sort_order: number
  is_deleted: boolean
  visit_types: VisitType[]
  is_enabled: boolean
  is_unavailable: boolean
  unavailable_reason: string | null
  unavailable_until: string | null
  has_available_doctor: boolean
  doctors: ClinicDoctor[]
}
type ClinicAdminData = { facility_id: number; facility_name: string; items: ClinicRow[] }
type Doctor = { id: string; username: string; email: string }
type AuditEntry = {
  id: number
  occurred_at: string
  actor_username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string
}

type Props = {
  csrfToken: string
  canManageCatalog: boolean
  canManageFacility: boolean
}

const EMPTY_CLINIC_FORM = {
  code: '',
  name: '',
  sort_order: 0,
  visit_type_ids: [] as number[],
}

function requestHeaders(csrfToken: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }
}

function ClinicAdmin({ csrfToken, canManageCatalog, canManageFacility }: Props) {
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [facilityId, setFacilityId] = useState<number | null>(null)
  const [clinicData, setClinicData] = useState<ClinicAdminData | null>(null)
  const [catalog, setCatalog] = useState<ClinicRow[]>([])
  const [visitTypes, setVisitTypes] = useState<VisitType[]>([])
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([])
  const [doctors, setDoctors] = useState<Doctor[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeTab, setActiveTab] = useState('clinics')
  const [selectedClinicIds, setSelectedClinicIds] = useState<number[]>([])
  const [clinicModalOpen, setClinicModalOpen] = useState(false)
  const [editingClinic, setEditingClinic] = useState<ClinicRow | null>(null)
  const [clinicForm, setClinicForm] = useState(EMPTY_CLINIC_FORM)
  const [facilityModalOpen, setFacilityModalOpen] = useState(false)
  const [facilityName, setFacilityName] = useState('')
  const [visitTypeModalOpen, setVisitTypeModalOpen] = useState(false)
  const [visitTypeName, setVisitTypeName] = useState('')
  const [visitTypeColor, setVisitTypeColor] = useState('#F26B6B')
  const [unavailableClinic, setUnavailableClinic] = useState<ClinicRow | null>(null)
  const [unavailableReason, setUnavailableReason] = useState('')
  const [unavailableUntil, setUnavailableUntil] = useState<string | null>(null)
  const [doctorClinic, setDoctorClinic] = useState<ClinicRow | null>(null)
  const [doctorId, setDoctorId] = useState<string | null>(null)
  const [doctorLeaveFrom, setDoctorLeaveFrom] = useState<string | null>(null)
  const [doctorLeaveTo, setDoctorLeaveTo] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const nextFacilities = canManageFacility
        ? await apiRequest<Facility[]>('/clinics/facilities')
        : []
      setFacilities(nextFacilities)
      const selectedFacility =
        nextFacilities.find((facility) => facility.id === facilityId) ?? nextFacilities[0]
      const nextFacilityId = selectedFacility?.id ?? null
      if (facilityId !== nextFacilityId) setFacilityId(nextFacilityId)

      const [nextFacilityClinics, nextCatalog, nextVisitTypes] = await Promise.all([
        canManageFacility && nextFacilityId !== null
          ? apiRequest<ClinicAdminData>(`/clinics/admin?facility_id=${nextFacilityId}`)
          : Promise.resolve(null),
        canManageCatalog ? apiRequest<ClinicRow[]>('/clinics/catalog') : Promise.resolve([]),
        canManageCatalog ? apiRequest<VisitType[]>('/clinics/visit-types') : Promise.resolve([]),
      ])
      setClinicData(nextFacilityClinics)
      setCatalog(nextCatalog)
      setVisitTypes(nextVisitTypes)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load clinic settings.')
    } finally {
      setLoading(false)
    }
  }, [canManageCatalog, canManageFacility, facilityId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const handleDataChanged = (event: Event) => {
      if (!(event instanceof CustomEvent)) return
      const changes = event.detail as SystemEvent[]
      if (changes.some((change) => change.category === 'configuration')) void refresh()
    }
    window.addEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
    window.addEventListener(SYSTEM_MANUAL_REFRESH_EVENT, refresh)
    return () => {
      window.removeEventListener(SYSTEM_DATA_CHANGED_EVENT, handleDataChanged)
      window.removeEventListener(SYSTEM_MANUAL_REFRESH_EVENT, refresh)
    }
  }, [refresh])

  const loadAudit = useCallback(async () => {
    if (facilityId === null) return
    try {
      setAuditEntries(
        await apiRequest<AuditEntry[]>(`/clinics/audit?facility_id=${facilityId}&limit=100`),
      )
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load clinic history.')
    }
  }, [facilityId])

  useEffect(() => {
    if (activeTab === 'audit') void loadAudit()
  }, [activeTab, loadAudit])

  const listForTable = useMemo(() => {
    if (canManageFacility && clinicData) return clinicData.items
    return catalog.map((clinic) => ({
      ...clinic,
      is_enabled: false,
      is_unavailable: false,
      unavailable_reason: null,
      unavailable_until: null,
      has_available_doctor: false,
      doctors: [],
    }))
  }, [canManageFacility, catalog, clinicData])

  const openNewClinic = () => {
    setEditingClinic(null)
    setClinicForm(EMPTY_CLINIC_FORM)
    setClinicModalOpen(true)
  }

  const openEditClinic = (clinic: ClinicRow) => {
    setEditingClinic(clinic)
    setClinicForm({
      code: clinic.code,
      name: clinic.name,
      sort_order: clinic.sort_order,
      visit_type_ids: clinic.visit_types.map((visitType) => visitType.id),
    })
    setClinicModalOpen(true)
  }

  const saveClinic = async () => {
    setError('')
    setSuccess('')
    if (!clinicForm.code.trim() && !editingClinic) {
      setError('Enter a clinic code.')
      return
    }
    if (!clinicForm.name.trim() || clinicForm.visit_type_ids.length === 0) {
      setError('Enter a clinic name and select at least one visit type.')
      return
    }
    setSaving(true)
    try {
      if (editingClinic) {
        await apiRequest(`/clinics/catalog/${editingClinic.id}`, {
          method: 'PATCH',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify({
            name: clinicForm.name,
            sort_order: clinicForm.sort_order,
            visit_type_ids: clinicForm.visit_type_ids,
          }),
        })
      } else {
        await apiRequest('/clinics/catalog', {
          method: 'POST',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify(clinicForm),
        })
      }
      setClinicModalOpen(false)
      setSuccess(editingClinic ? 'Clinic catalog updated.' : 'Clinic added to the master catalog.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save clinic.')
    } finally {
      setSaving(false)
    }
  }

  const setClinicEnabled = async (clinic: ClinicRow, enabled: boolean) => {
    if (facilityId === null) return
    setSaving(true)
    setError('')
    try {
      await apiRequest(`/clinics/facilities/${facilityId}/clinics/${clinic.id}`, {
        method: 'PATCH',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          is_enabled: enabled,
          is_unavailable: clinic.is_unavailable,
          unavailable_reason: clinic.unavailable_reason,
          unavailable_until: clinic.unavailable_until,
        }),
      })
      setSuccess(`${clinic.name} ${enabled ? 'enabled' : 'disabled'} for this facility.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update clinic status.')
    } finally {
      setSaving(false)
    }
  }

  const saveUnavailable = async () => {
    if (!unavailableClinic || facilityId === null) return
    if (!unavailableReason.trim()) {
      setError('Enter a reason for the temporary closure.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiRequest(`/clinics/facilities/${facilityId}/clinics/${unavailableClinic.id}`, {
        method: 'PATCH',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          is_enabled: unavailableClinic.is_enabled,
          is_unavailable: true,
          unavailable_reason: unavailableReason.trim(),
          unavailable_until: unavailableUntil ? new Date(unavailableUntil).toISOString() : null,
        }),
      })
      setUnavailableClinic(null)
      setUnavailableReason('')
      setUnavailableUntil(null)
      setSuccess(`${unavailableClinic.name} marked temporarily unavailable.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to mark clinic unavailable.')
    } finally {
      setSaving(false)
    }
  }

  const reopenClinic = async (clinic: ClinicRow) => {
    if (facilityId === null) return
    setSaving(true)
    try {
      await apiRequest(`/clinics/facilities/${facilityId}/clinics/${clinic.id}`, {
        method: 'PATCH',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          is_enabled: clinic.is_enabled,
          is_unavailable: false,
        }),
      })
      setSuccess(`${clinic.name} is available again.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to reopen clinic.')
    } finally {
      setSaving(false)
    }
  }

  const deactivateClinic = async (clinic: ClinicRow) => {
    setSaving(true)
    setError('')
    try {
      await apiRequest(`/clinics/catalog/${clinic.id}`, {
        method: 'PATCH',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ is_deleted: true }),
      })
      setSuccess(`${clinic.name} deactivated in the master catalog.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to deactivate clinic.')
    } finally {
      setSaving(false)
    }
  }

  const bulkSetEnabled = async (enabled: boolean) => {
    if (facilityId === null || selectedClinicIds.length === 0) return
    setSaving(true)
    setError('')
    try {
      await Promise.all(
        selectedClinicIds.map((id) => {
          const clinic = clinicData?.items.find((item) => item.id === id)
          if (!clinic) return Promise.resolve()
          return apiRequest(`/clinics/facilities/${facilityId}/clinics/${id}`, {
            method: 'PATCH',
            headers: requestHeaders(csrfToken),
            body: JSON.stringify({
              is_enabled: enabled,
              is_unavailable: clinic.is_unavailable,
              unavailable_reason: clinic.unavailable_reason,
              unavailable_until: clinic.unavailable_until,
            }),
          })
        }),
      )
      setSelectedClinicIds([])
      setSuccess(`Selected clinics ${enabled ? 'enabled' : 'disabled'}.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update selected clinics.')
    } finally {
      setSaving(false)
    }
  }

  const openDoctorDialog = async (clinic: ClinicRow) => {
    if (facilityId === null) return
    setError('')
    try {
      setDoctors(
        await apiRequest<Doctor[]>(`/clinics/facilities/${facilityId}/doctors`),
      )
      setDoctorClinic(clinic)
      setDoctorId(null)
      setDoctorLeaveFrom(null)
      setDoctorLeaveTo(null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load facility doctors.')
    }
  }

  const saveDoctorAssignment = async () => {
    if (!doctorClinic || !doctorId || facilityId === null) {
      setError('Select a doctor to assign.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiRequest(
        `/clinics/facilities/${facilityId}/clinics/${doctorClinic.id}/doctors`,
        {
          method: 'POST',
          headers: requestHeaders(csrfToken),
          body: JSON.stringify({
            user_id: doctorId,
            on_leave_from: doctorLeaveFrom,
            on_leave_to: doctorLeaveTo,
            is_active: true,
          }),
        },
      )
      setSuccess(`Doctor assigned to ${doctorClinic.name}.`)
      setDoctorClinic(null)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to assign doctor.')
    } finally {
      setSaving(false)
    }
  }

  const createFacility = async () => {
    if (!facilityName.trim()) {
      setError('Enter a facility name.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiRequest('/clinics/facilities', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ name: facilityName.trim() }),
      })
      setFacilityName('')
      setFacilityModalOpen(false)
      setSuccess('Facility created. Enable clinics for it from the facility selector.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create facility.')
    } finally {
      setSaving(false)
    }
  }

  const createVisitType = async () => {
    if (!visitTypeName.trim()) {
      setError('Enter a visit type name.')
      return
    }
    setSaving(true)
    try {
      await apiRequest('/clinics/visit-types', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ name: visitTypeName.trim(), color_hex: visitTypeColor }),
      })
      setVisitTypeName('')
      setVisitTypeModalOpen(false)
      setSuccess('Visit type added.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create visit type.')
    } finally {
      setSaving(false)
    }
  }

  const clinicColumns: TableColumnsType<ClinicRow> = [
    {
      title: 'Clinic',
      key: 'clinic',
      render: (_, clinic) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{clinic.name}</Text>
          <Text type="secondary">{clinic.code}</Text>
        </Space>
      ),
    },
    {
      title: 'Visit Types',
      key: 'visit_types',
      render: (_, clinic) => (
        <Space wrap size={[4, 4]}>
          {clinic.visit_types.map((visitType) => (
            <Tag color={visitType.color_hex} key={visitType.id}>{visitType.name}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: 'Doctors',
      key: 'doctors',
      render: (_, clinic) => (
        <Space wrap>
          {clinic.doctors.map((doctor) => (
            <Tag key={doctor.id} color={doctor.is_active ? 'blue' : 'default'}>
              {doctor.username}
            </Tag>
          ))}
          {canManageFacility && (
            <Button size="small" onClick={() => void openDoctorDialog(clinic)}>Assign</Button>
          )}
        </Space>
      ),
    },
    {
      title: 'Status',
      key: 'status',
      render: (_, clinic) => (
        <Space>
          {canManageFacility && (
            <Switch
              checked={clinic.is_enabled}
              disabled={clinic.is_deleted || saving}
              onChange={(checked) => void setClinicEnabled(clinic, checked)}
              aria-label={`${clinic.is_enabled ? 'Disable' : 'Enable'} ${clinic.name}`}
            />
          )}
          {clinic.is_deleted ? (
            <Tag color="default">Deactivated</Tag>
          ) : clinic.is_unavailable ? (
            <Tag color="orange">Temporarily unavailable</Tag>
          ) : clinic.is_enabled ? (
            <Tag color="green">Enabled</Tag>
          ) : (
            <Tag>Not needed</Tag>
          )}
          {clinic.is_unavailable && clinic.unavailable_reason && (
            <Text type="secondary">{clinic.unavailable_reason}</Text>
          )}
        </Space>
      ),
    },
    {
      title: 'Unavailable until',
      dataIndex: 'unavailable_until',
      key: 'unavailable_until',
      render: (value: string | null) => value ? new Date(value).toLocaleString() : '—',
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, clinic) => (
        <Space wrap>
          {canManageCatalog && (
            <Button size="small" onClick={() => openEditClinic(clinic)}>Edit</Button>
          )}
          {canManageFacility && !clinic.is_deleted && (
            clinic.is_unavailable ? (
              <Button size="small" onClick={() => void reopenClinic(clinic)}>Reopen</Button>
            ) : (
              <Button size="small" onClick={() => {
                setUnavailableClinic(clinic)
                setUnavailableReason('')
                setUnavailableUntil(null)
              }}>
                Mark unavailable
              </Button>
            )
          )}
          {canManageCatalog && !clinic.is_deleted && (
            <Button size="small" danger onClick={() => void deactivateClinic(clinic)}>
              Deactivate
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const auditColumns: TableColumnsType<AuditEntry> = [
    { title: 'Date', dataIndex: 'occurred_at', key: 'occurred_at', render: (value: string) => new Date(value).toLocaleString() },
    { title: 'Action', dataIndex: 'action', key: 'action' },
    { title: 'Resource', dataIndex: 'resource_type', key: 'resource_type' },
    { title: 'Reference', dataIndex: 'resource_id', key: 'resource_id' },
    { title: 'Performed by', dataIndex: 'actor_username', key: 'actor_username', render: (value: string | null) => value ?? 'System' },
  ]

  return (
    <div className="clinic-admin">
      <div className="page-heading">
        <div>
          <Text className="eyebrow">CONFIGURATION</Text>
          <Title level={3}>Clinic management</Title>
          <Text type="secondary">
            Manage the master clinic catalog and the clinics available at each facility.
          </Text>
        </div>
        <Space wrap>
          {canManageFacility && facilities.length > 1 && (
            <Select
              aria-label="Facility"
              value={facilityId ?? undefined}
              onChange={(value) => setFacilityId(value)}
              options={facilities.map((facility) => ({
                value: facility.id,
                label: facility.name,
              }))}
              style={{ minWidth: 220 }}
            />
          )}
          {canManageCatalog && (
            <>
              <Button onClick={() => setVisitTypeModalOpen(true)}>Manage visit types</Button>
              <Button onClick={() => setFacilityModalOpen(true)}>Add facility</Button>
              <Button type="primary" onClick={openNewClinic}>Add clinic</Button>
            </>
          )}
        </Space>
      </div>
      {error && <Alert showIcon type="error" title={error} closable onClose={() => setError('')} />}
      {success && <Alert showIcon type="success" title={success} closable onClose={() => setSuccess('')} />}
      {clinicData && (
        <Alert
          showIcon
          type="info"
          title={`Facility: ${clinicData.facility_name}. Disabled clinics are hidden from OPD registration; temporary closures expire automatically.`}
          className="admin-notice"
        />
      )}
      {!canManageCatalog && !canManageFacility && (
        <Alert showIcon type="warning" title="Your account does not have clinic configuration privileges." />
      )}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'clinics',
            label: 'Clinics',
            children: (
              <>
                {canManageFacility && selectedClinicIds.length > 0 && (
                  <Space className="queue-toolbar">
                    <Text>{selectedClinicIds.length} selected</Text>
                    <Button onClick={() => void bulkSetEnabled(true)} loading={saving}>Bulk enable</Button>
                    <Button onClick={() => void bulkSetEnabled(false)} loading={saving}>Bulk disable</Button>
                  </Space>
                )}
                <Table
                  rowKey="id"
                  loading={loading}
                  columns={clinicColumns}
                  dataSource={listForTable}
                  rowSelection={canManageFacility ? {
                    selectedRowKeys: selectedClinicIds,
                    onChange: (keys) => setSelectedClinicIds(keys.map(Number)),
                  } : undefined}
                  pagination={{ pageSize: 20 }}
                  scroll={{ x: 1100 }}
                />
              </>
            ),
          },
          {
            key: 'audit',
            label: 'Audit history',
            children: (
              <Table
                rowKey="id"
                loading={loading}
                columns={auditColumns}
                dataSource={auditEntries}
                pagination={{ pageSize: 20 }}
                scroll={{ x: 800 }}
              />
            ),
          },
        ]}
      />

      <Modal
        title={editingClinic ? `Edit clinic: ${editingClinic.code}` : 'Add clinic to master catalog'}
        open={clinicModalOpen}
        onCancel={() => setClinicModalOpen(false)}
        onOk={() => void saveClinic()}
        confirmLoading={saving}
        okText="Save clinic"
      >
        <Space orientation="vertical" className="modal-full-width">
          {!editingClinic && (
            <Input
              aria-label="Clinic code"
              placeholder="Unique clinic code"
              value={clinicForm.code}
              onChange={(event) => setClinicForm((form) => ({ ...form, code: event.target.value.toUpperCase() }))}
            />
          )}
          <Input
            aria-label="Clinic name"
            placeholder="Clinic name"
            value={clinicForm.name}
            onChange={(event) => setClinicForm((form) => ({ ...form, name: event.target.value }))}
          />
          <Input
            aria-label="Sort order"
            type="number"
            min={0}
            value={clinicForm.sort_order}
            onChange={(event) => setClinicForm((form) => ({ ...form, sort_order: Number(event.target.value) || 0 }))}
          />
          <Select
            aria-label="Clinic visit types"
            mode="multiple"
            placeholder="Select visit types"
            value={clinicForm.visit_type_ids}
            onChange={(values: number[]) => setClinicForm((form) => ({ ...form, visit_type_ids: values }))}
            options={visitTypes.filter((visitType) => visitType.is_active).map((visitType) => ({
              label: visitType.name,
              value: visitType.id,
            }))}
          />
        </Space>
      </Modal>

      <Modal
        title="Add facility"
        open={facilityModalOpen}
        onCancel={() => setFacilityModalOpen(false)}
        onOk={() => void createFacility()}
        confirmLoading={saving}
        okText="Create facility"
      >
        <Input
          aria-label="Facility name"
          placeholder="Facility name"
          value={facilityName}
          onChange={(event) => setFacilityName(event.target.value)}
        />
      </Modal>

      <Modal
        title="Add visit type"
        open={visitTypeModalOpen}
        onCancel={() => setVisitTypeModalOpen(false)}
        onOk={() => void createVisitType()}
        confirmLoading={saving}
        okText="Add visit type"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Visit type name"
            placeholder="Visit type name"
            value={visitTypeName}
            onChange={(event) => setVisitTypeName(event.target.value)}
          />
          <Input
            aria-label="Visit type color"
            type="color"
            value={visitTypeColor}
            onChange={(event) => setVisitTypeColor(event.target.value)}
          />
          <Space wrap>
            {visitTypes.map((visitType) => (
              <Tag color={visitType.color_hex} key={visitType.id}>{visitType.name}</Tag>
            ))}
          </Space>
        </Space>
      </Modal>

      <Modal
        title={`Temporarily unavailable: ${unavailableClinic?.name ?? ''}`}
        open={unavailableClinic !== null}
        onCancel={() => setUnavailableClinic(null)}
        onOk={() => void saveUnavailable()}
        confirmLoading={saving}
        okText="Mark unavailable"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Reason for temporary unavailability"
            placeholder="Reason (required)"
            value={unavailableReason}
            onChange={(event) => setUnavailableReason(event.target.value)}
          />
          <label>
            Reopen automatically at
            <Input
              type="datetime-local"
              value={unavailableUntil ?? ''}
              onChange={(event) => setUnavailableUntil(event.target.value || null)}
            />
          </label>
          <Text type="secondary">Leave the date empty to keep the clinic closed until it is reopened manually.</Text>
        </Space>
      </Modal>

      <Modal
        title={`Assign a doctor: ${doctorClinic?.name ?? ''}`}
        open={doctorClinic !== null}
        onCancel={() => setDoctorClinic(null)}
        onOk={() => void saveDoctorAssignment()}
        confirmLoading={saving}
        okText="Assign doctor"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Select
            aria-label="Choose doctor"
            placeholder="Choose a doctor at this facility"
            value={doctorId}
            onChange={setDoctorId}
            options={doctors.map((doctor) => ({
              label: `${doctor.username} (${doctor.email})`,
              value: doctor.id,
            }))}
          />
          <label>
            Leave from
            <Input type="date" value={doctorLeaveFrom ?? ''} onChange={(event) => setDoctorLeaveFrom(event.target.value || null)} />
          </label>
          <label>
            Leave until
            <Input type="date" value={doctorLeaveTo ?? ''} onChange={(event) => setDoctorLeaveTo(event.target.value || null)} />
          </label>
        </Space>
      </Modal>
    </div>
  )
}

export default ClinicAdmin
