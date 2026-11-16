import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { apiRequest } from './api'

const { Text, Title } = Typography

type UserRecord = {
  id: string
  username: string
  email: string
  department: string | null
  is_system_owner: boolean
  roles: string[]
  is_active: boolean
  permission_overrides: Record<string, boolean>
}

type RoleRecord = {
  id: string
  name: string
  description: string
  permissions: string[]
  is_system: boolean
}

type PermissionRecord = {
  id: string
  key: string
  description: string
  is_system: boolean
}

type AuditLogRecord = {
  id: number
  occurred_at: string
  actor_username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string
}

type AuditLogPage = {
  items: AuditLogRecord[]
  total: number
  limit: number
  offset: number
}

const AUDIT_PAGE_SIZE = 20

type AdminConsoleProps = {
  csrfToken: string
  currentUserId: string
  canManageUsers: boolean
  canManageRoles: boolean
  canViewAudit: boolean
  onSessionRevoked: () => void
}

function requestHeaders(csrfToken: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  }
}

function AdminConsole({
  csrfToken,
  currentUserId,
  canManageUsers,
  canManageRoles,
  canViewAudit,
  onSessionRevoked,
}: AdminConsoleProps) {
  const [users, setUsers] = useState<UserRecord[]>([])
  const [roles, setRoles] = useState<RoleRecord[]>([])
  const [permissions, setPermissions] = useState<PermissionRecord[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([])
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditTotal, setAuditTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [department, setDepartment] = useState('')
  const [password, setPassword] = useState('')
  const [newUserRoleIds, setNewUserRoleIds] = useState<string[]>([])
  const [newRoleName, setNewRoleName] = useState('')
  const [newRoleDescription, setNewRoleDescription] = useState('')
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null)
  const [editingUserRoleIds, setEditingUserRoleIds] = useState<string[]>([])
  const [editingUserProfile, setEditingUserProfile] = useState<UserRecord | null>(null)
  const [userProfileForm, setUserProfileForm] = useState({
    username: '',
    email: '',
    department: '',
  })
  const [editingUserOverrides, setEditingUserOverrides] = useState<UserRecord | null>(null)
  const [userOverrideGrants, setUserOverrideGrants] = useState<string[]>([])
  const [userOverrideDenies, setUserOverrideDenies] = useState<string[]>([])
  const [resettingUser, setResettingUser] = useState<UserRecord | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [editingRole, setEditingRole] = useState<RoleRecord | null>(null)
  const [editingPermissionKeys, setEditingPermissionKeys] = useState<string[]>([])
  const [editingRoleDetails, setEditingRoleDetails] = useState<RoleRecord | null>(null)
  const [roleDetailsForm, setRoleDetailsForm] = useState({ name: '', description: '' })
  const [newPermissionKey, setNewPermissionKey] = useState('')
  const [newPermissionDescription, setNewPermissionDescription] = useState('')
  const [editingPermission, setEditingPermission] = useState<PermissionRecord | null>(null)
  const [permissionForm, setPermissionForm] = useState({ key: '', description: '' })

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [nextUsers, nextRoles, nextPermissions, nextAuditPage] = await Promise.all([
        canManageUsers ? apiRequest<UserRecord[]>('/auth/users') : Promise.resolve([]),
        canManageUsers || canManageRoles
          ? apiRequest<RoleRecord[]>('/auth/roles')
          : Promise.resolve([]),
        canManageRoles ? apiRequest<PermissionRecord[]>('/auth/permissions') : Promise.resolve([]),
        canViewAudit
          ? apiRequest<AuditLogPage>(`/auth/audit-logs?limit=${AUDIT_PAGE_SIZE}&offset=0`)
          : Promise.resolve(null),
      ])
      setUsers(nextUsers)
      setRoles(nextRoles)
      setPermissions(nextPermissions)
      setAuditLogs(nextAuditPage?.items ?? [])
      setAuditOffset(0)
      setAuditTotal(nextAuditPage?.total ?? 0)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load administration data.')
    } finally {
      setLoading(false)
    }
  }, [canManageUsers, canManageRoles, canViewAudit])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const loadAuditPage = async (offset: number) => {
    setError('')
    setLoading(true)
    try {
      const page = await apiRequest<AuditLogPage>(
        `/auth/audit-logs?limit=${AUDIT_PAGE_SIZE}&offset=${offset}`,
      )
      setAuditLogs(page.items)
      setAuditOffset(offset)
      setAuditTotal(page.total)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load audit logs.')
    } finally {
      setLoading(false)
    }
  }

  const assignableRoles = useMemo(
    () => roles.filter((role) => canManageRoles || role.name !== 'SuperAdmin'),
    [canManageRoles, roles],
  )

  const permissionGroups = useMemo(() => {
    const groups = new Map<string, PermissionRecord[]>()
    for (const permission of permissions) {
      const department = permission.key.split('.')[0]
      const group = groups.get(department) ?? []
      group.push(permission)
      groups.set(department, group)
    }
    return [...groups.entries()].map(([key, entries]) => ({
      key,
      label: `${key.replaceAll('-', ' ')} (${entries.length})`,
      children: (
        <Checkbox.Group
          value={editingPermissionKeys}
          options={entries.map((permission) => ({
            label: permission.description,
            value: permission.key,
          }))}
          onChange={(values) => {
            const groupKeys = new Set(entries.map((permission) => permission.key))
            const selectedInGroup = values.filter(
              (value): value is string => typeof value === 'string',
            )
            setEditingPermissionKeys((current) => [
              ...current.filter((key) => !groupKeys.has(key)),
              ...selectedInGroup,
            ])
          }}
        />
      ),
    }))
  }, [permissions, editingPermissionKeys])

  const handleCreateUser = async () => {
    setError('')
    setSuccess('')
    if (!username.trim() || !email.trim() || password.length < 14 || newUserRoleIds.length === 0) {
      setError('Enter a username, email, password of at least 14 characters, and at least one role.')
      return
    }
    setSaving(true)
    try {
      await apiRequest<UserRecord>('/auth/users', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          department: department.trim() || null,
          password,
          role_ids: newUserRoleIds,
        }),
      })
      setUsername('')
      setEmail('')
      setDepartment('')
      setPassword('')
      setNewUserRoleIds([])
      setSuccess('User created. Share the initial password with them through an approved secure channel.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create user.')
    } finally {
      setSaving(false)
    }
  }

  const handleCreateRole = async () => {
    setError('')
    setSuccess('')
    if (!newRoleName.trim()) {
      setError('Enter a role name.')
      return
    }
    setSaving(true)
    try {
      await apiRequest<RoleRecord>('/auth/roles', {
        method: 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          name: newRoleName.trim(),
          description: newRoleDescription.trim(),
          permission_keys: [],
        }),
      })
      setNewRoleName('')
      setNewRoleDescription('')
      setSuccess('Role created. Edit its privileges before assigning it to users.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to create role.')
    } finally {
      setSaving(false)
    }
  }

  const saveUserRoles = async () => {
    if (!editingUser) return
    setError('')
    setSaving(true)
    try {
      const removingOwnSuperAdminRole =
        editingUser.id === currentUserId &&
        editingUser.roles.includes('SuperAdmin') &&
        !editingUserRoleIds.some((roleId) =>
          roles.some((role) => role.id === roleId && role.name === 'SuperAdmin'),
        )
      await apiRequest<UserRecord>(`/auth/users/${editingUser.id}/roles`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ role_ids: editingUserRoleIds }),
      })
      setEditingUser(null)
      setSuccess(`Roles updated for ${editingUser.username}.`)
      if (removingOwnSuperAdminRole) {
        onSessionRevoked()
        return
      }
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update user roles.')
    } finally {
      setSaving(false)
    }
  }

  const saveUserProfile = async () => {
    if (!editingUserProfile) return
    setError('')
    setSaving(true)
    try {
      await apiRequest<UserRecord>(`/auth/users/${editingUserProfile.id}`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          username: userProfileForm.username,
          email: userProfileForm.email,
          department: userProfileForm.department.trim() || null,
        }),
      })
      setEditingUserProfile(null)
      setSuccess(`Profile updated for ${userProfileForm.username}.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update user.')
    } finally {
      setSaving(false)
    }
  }

  const saveUserPermissionOverrides = async () => {
    if (!editingUserOverrides) return
    setError('')
    setSaving(true)
    try {
      const overrides: Record<string, boolean> = {}
      userOverrideGrants.forEach((key) => {
        overrides[key] = true
      })
      userOverrideDenies.forEach((key) => {
        overrides[key] = false
      })
      await apiRequest<UserRecord>(`/auth/users/${editingUserOverrides.id}/permissions`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ overrides }),
      })
      setEditingUserOverrides(null)
      setSuccess(`Individual permissions updated for ${editingUserOverrides.username}.`)
      await refresh()
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : 'Unable to update individual permissions.',
      )
    } finally {
      setSaving(false)
    }
  }

  const saveRolePermissions = async () => {
    if (!editingRole) return
    setError('')
    setSaving(true)
    try {
      await apiRequest<RoleRecord>(`/auth/roles/${editingRole.id}/permissions`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ permission_keys: editingPermissionKeys }),
      })
      setEditingRole(null)
      setSuccess(`Privileges updated for ${editingRole.name}.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update privileges.')
    } finally {
      setSaving(false)
    }
  }

  const saveRoleDetails = async () => {
    if (!editingRoleDetails) return
    setError('')
    setSaving(true)
    try {
      await apiRequest<RoleRecord>(`/auth/roles/${editingRoleDetails.id}`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify(roleDetailsForm),
      })
      setEditingRoleDetails(null)
      setSuccess(`Role ${roleDetailsForm.name} updated.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update role.')
    } finally {
      setSaving(false)
    }
  }

  const deleteRole = async (role: RoleRecord) => {
    setError('')
    setSaving(true)
    try {
      await apiRequest<void>(`/auth/roles/${role.id}`, {
        method: 'DELETE',
        headers: requestHeaders(csrfToken),
      })
      setSuccess(`Role ${role.name} deleted.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to delete role.')
    } finally {
      setSaving(false)
    }
  }

  const savePermission = async (form = permissionForm) => {
    setError('')
    if (!form.key.trim() || !form.description.trim()) {
      setError('Enter a permission key and description.')
      return
    }
    setSaving(true)
    try {
      const path = editingPermission
        ? `/auth/permissions/${editingPermission.id}`
        : '/auth/permissions'
      await apiRequest<PermissionRecord>(path, {
        method: editingPermission ? 'PUT' : 'POST',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({
          key: form.key.trim(),
          description: form.description.trim(),
        }),
      })
      setEditingPermission(null)
      setNewPermissionKey('')
      setNewPermissionDescription('')
      setPermissionForm({ key: '', description: '' })
      setSuccess(editingPermission ? 'Permission updated.' : 'Permission created.')
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to save permission.')
    } finally {
      setSaving(false)
    }
  }

  const deletePermission = async (permission: PermissionRecord) => {
    setError('')
    setSaving(true)
    try {
      await apiRequest<void>(`/auth/permissions/${permission.id}`, {
        method: 'DELETE',
        headers: requestHeaders(csrfToken),
      })
      setSuccess(`Permission ${permission.key} deleted.`)
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to delete permission.')
    } finally {
      setSaving(false)
    }
  }

  const changeUserStatus = async (user: UserRecord, isActive: boolean) => {
    setError('')
    setSuccess('')
    try {
      await apiRequest<UserRecord>(`/auth/users/${user.id}/status`, {
        method: 'PATCH',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ is_active: isActive }),
      })
      setSuccess(`${user.username} ${isActive ? 'activated' : 'deactivated'}.`)
      if (user.id === currentUserId && !isActive) {
        onSessionRevoked()
        return
      }
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to update account status.')
    }
  }

  const resetUserPassword = async () => {
    if (!resettingUser) return
    setError('')
    setSuccess('')
    if (resetPassword.length < 14) {
      setError('The replacement password must be at least 14 characters.')
      return
    }
    setSaving(true)
    try {
      await apiRequest<void>(`/auth/users/${resettingUser.id}/password`, {
        method: 'PUT',
        headers: requestHeaders(csrfToken),
        body: JSON.stringify({ password: resetPassword }),
      })
      setSuccess(`Password reset for ${resettingUser.username}. Share it through an approved secure channel.`)
      const resetOwnPassword = resettingUser.id === currentUserId
      setResettingUser(null)
      setResetPassword('')
      if (resetOwnPassword) {
        onSessionRevoked()
        return
      }
      await refresh()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to reset the password.')
    } finally {
      setSaving(false)
    }
  }

  const userColumns: TableColumnsType<UserRecord> = [
    { title: 'USERNAME', dataIndex: 'username', key: 'username' },
    { title: 'EMAIL', dataIndex: 'email', key: 'email' },
    { title: 'DEPARTMENT', dataIndex: 'department', key: 'department' },
    {
      title: 'ROLES',
      dataIndex: 'roles',
      key: 'roles',
      render: (names: string[], user) => (
        <Space size={4}>
          {names.map((name) => <Tag key={name}>{name}</Tag>)}
          {user.is_system_owner && <Tag color="gold">SYSTEM OWNER</Tag>}
        </Space>
      ),
    },
    {
      title: 'ACTIVE',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive: boolean, user) => (
        <Switch
          checked={isActive}
          disabled={
            user.is_system_owner ||
            (!canManageRoles &&
              (user.id === currentUserId || user.roles.includes('SuperAdmin')))
          }
          aria-label={`Set ${user.username} active`}
          onChange={(nextStatus) => void changeUserStatus(user, nextStatus)}
        />
      ),
    },
    {
      title: '',
      key: 'actions',
      align: 'right',
      render: (_, user) => (
        <Space>
          <Button
            disabled={
              (user.is_system_owner && user.id !== currentUserId) ||
              (!canManageRoles && user.roles.includes('SuperAdmin'))
            }
            onClick={() => {
              setEditingUserProfile(user)
              setUserProfileForm({
                username: user.username,
                email: user.email,
                department: user.department ?? '',
              })
            }}
          >
            Edit details
          </Button>
          <Button
            disabled={
              user.is_system_owner ||
              (!canManageRoles && user.roles.includes('SuperAdmin'))
            }
            onClick={() => {
              setEditingUser(user)
              setEditingUserRoleIds(
                roles.filter((role) => user.roles.includes(role.name)).map((role) => role.id),
              )
            }}
          >
            Assign roles
          </Button>
          <Button
            disabled={
              (user.is_system_owner && user.id !== currentUserId) ||
              (!canManageRoles && user.roles.includes('SuperAdmin'))
            }
            onClick={() => {
              setResettingUser(user)
              setResetPassword('')
            }}
          >
            Reset password
          </Button>
          {canManageRoles && (
            <Button
              disabled={user.is_system_owner}
              onClick={() => {
                setEditingUserOverrides(user)
                setUserOverrideGrants(
                  Object.entries(user.permission_overrides)
                    .filter(([, isGranted]) => isGranted)
                    .map(([key]) => key),
                )
                setUserOverrideDenies(
                  Object.entries(user.permission_overrides)
                    .filter(([, isGranted]) => !isGranted)
                    .map(([key]) => key),
                )
              }}
            >
              Individual access
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const auditColumns: TableColumnsType<AuditLogRecord> = [
    {
      title: 'WHEN',
      dataIndex: 'occurred_at',
      key: 'occurred_at',
      render: (occurredAt: string) => new Date(occurredAt).toLocaleString(),
    },
    {
      title: 'ACTOR',
      dataIndex: 'actor_username',
      key: 'actor_username',
      render: (username: string | null) => username ?? 'System / unknown',
    },
    { title: 'ACTION', dataIndex: 'action', key: 'action' },
    {
      title: 'RESOURCE',
      key: 'resource',
      render: (_, record) =>
        record.resource_id ? `${record.resource_type} · ${record.resource_id}` : record.resource_type,
    },
    { title: 'OUTCOME', dataIndex: 'outcome', key: 'outcome' },
  ]

  const roleColumns: TableColumnsType<RoleRecord> = [
    { title: 'ROLE', dataIndex: 'name', key: 'name' },
    { title: 'DESCRIPTION', dataIndex: 'description', key: 'description' },
    {
      title: 'PRIVILEGES',
      dataIndex: 'permissions',
      key: 'permissions',
      render: (keys: string[]) => keys.length,
    },
    {
      title: '',
      key: 'actions',
      align: 'right',
      render: (_, role) => (
        <Space>
          {!role.is_system && (
            <>
              <Button
                onClick={() => {
                  setEditingRoleDetails(role)
                  setRoleDetailsForm({ name: role.name, description: role.description })
                }}
              >
                Edit details
              </Button>
              <Button
                onClick={() => {
                  setEditingRole(role)
                  setEditingPermissionKeys(role.permissions)
                }}
              >
                Edit privileges
              </Button>
              <Popconfirm
                title={`Delete ${role.name}?`}
                description="Roles assigned to users cannot be deleted."
                onConfirm={() => void deleteRole(role)}
              >
                <Button danger loading={saving}>Delete</Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  const permissionColumns: TableColumnsType<PermissionRecord> = [
    { title: 'KEY', dataIndex: 'key', key: 'key' },
    { title: 'DESCRIPTION', dataIndex: 'description', key: 'description' },
    {
      title: 'TYPE',
      dataIndex: 'is_system',
      key: 'type',
      render: (isSystem: boolean) => <Tag>{isSystem ? 'Built-in' : 'Custom'}</Tag>,
    },
    {
      title: '',
      key: 'actions',
      align: 'right',
      render: (_, permission) => (
        <Space>
          <Button
            onClick={() => {
              setEditingPermission(permission)
              setPermissionForm({ key: permission.key, description: permission.description })
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title={`Delete ${permission.key}?`}
            description="Built-in or assigned permissions cannot be deleted."
            onConfirm={() => void deletePermission(permission)}
          >
            <Button danger disabled={permission.is_system} loading={saving}>Delete</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const tabs = [
    canManageUsers
      ? {
          key: 'users',
          label: 'Users',
          children: (
            <Space orientation="vertical" size={18} className="admin-content">
              <Card size="small" title="Create user">
                <Alert
                  type="info"
                  showIcon
                  title="Cash collection and refund approval are separated. A user cannot be assigned both privileges."
                  className="admin-notice"
                />
                <div className="admin-form-grid">
                  <Input
                    aria-label="Username"
                    placeholder="Username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                  />
                  <Input
                    aria-label="Email"
                    placeholder="Email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                  <Input
                    aria-label="Department"
                    placeholder="Department (optional)"
                    value={department}
                    onChange={(event) => setDepartment(event.target.value)}
                  />
                  <Input.Password
                    aria-label="Initial password"
                    placeholder="Initial password (14+ characters)"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <Select
                    mode="multiple"
                    aria-label="User roles"
                    placeholder="Assign one or more roles"
                    value={newUserRoleIds}
                    onChange={setNewUserRoleIds}
                    options={assignableRoles.map((role) => ({
                      label: role.name,
                      value: role.id,
                    }))}
                  />
                  <Button type="primary" loading={saving} onClick={() => void handleCreateUser()}>
                    Create user
                  </Button>
                </div>
              </Card>
              <Card size="small" title="System users">
                <Table
                  columns={userColumns}
                  dataSource={users}
                  loading={loading}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 760 }}
                />
              </Card>
            </Space>
          ),
        }
      : null,
    canManageRoles
      ? {
          key: 'roles',
          label: 'Roles & privileges',
          children: (
            <Space orientation="vertical" size={18} className="admin-content">
              <Card size="small" title="Create role">
                <div className="admin-form-grid">
                  <Input
                    aria-label="Role name"
                    placeholder="Role name"
                    value={newRoleName}
                    onChange={(event) => setNewRoleName(event.target.value)}
                  />
                  <Input
                    aria-label="Role description"
                    placeholder="Description"
                    value={newRoleDescription}
                    onChange={(event) => setNewRoleDescription(event.target.value)}
                  />
                  <Button type="primary" loading={saving} onClick={() => void handleCreateRole()}>
                    Create role
                  </Button>
                </div>
              </Card>
              <Card size="small" title="Available roles">
                <Table
                  columns={roleColumns}
                  dataSource={roles}
                  loading={loading}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 760 }}
                />
              </Card>
              <Card size="small" title="Permission catalog">
                <div className="admin-form-grid">
                  <Input
                    aria-label="New permission key"
                    placeholder="custom.permission.action"
                    value={newPermissionKey}
                    onChange={(event) => setNewPermissionKey(event.target.value)}
                  />
                  <Input
                    aria-label="New permission description"
                    placeholder="Permission description"
                    value={newPermissionDescription}
                    onChange={(event) => setNewPermissionDescription(event.target.value)}
                  />
                  <Button
                    type="primary"
                    loading={saving}
                    onClick={() =>
                      void savePermission({
                        key: newPermissionKey,
                        description: newPermissionDescription,
                      })
                    }
                  >
                    Create permission
                  </Button>
                </div>
                <Table
                  columns={permissionColumns}
                  dataSource={permissions}
                  loading={loading}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 900 }}
                />
              </Card>
            </Space>
          ),
        }
      : null,
    canViewAudit
      ? {
          key: 'audit',
          label: 'Audit log',
          children: (
            <Card size="small" title="Recorded system activity">
              <Table
                columns={auditColumns}
                dataSource={auditLogs}
                loading={loading}
                rowKey="id"
                pagination={{
                  current: Math.floor(auditOffset / AUDIT_PAGE_SIZE) + 1,
                  pageSize: AUDIT_PAGE_SIZE,
                  total: auditTotal,
                  onChange: (page, pageSize) =>
                    void loadAuditPage((page - 1) * pageSize),
                }}
                scroll={{ x: 760 }}
              />
            </Card>
          ),
        }
      : null,
  ].filter((tab): tab is NonNullable<typeof tab> => tab !== null)

  return (
    <div className="admin-console">
      <div className="page-heading">
        <div>
          <Text className="eyebrow">ACCESS CONTROL</Text>
          <Title level={3}>Administration and audit</Title>
          <Text type="secondary">
            Manage identities, configure least-privilege roles, or review recorded system activity.
          </Text>
        </div>
        <Button onClick={() => void refresh()} loading={loading}>Refresh</Button>
      </div>

      <Alert
        showIcon
        type="info"
        title="The designated System Owner cannot be deactivated or have SuperAdmin access or individual permissions removed."
        className="admin-notice"
      />
      <Alert
        showIcon
        type="info"
        title="Permanent deletion privileges are not defined in the supplied matrix. Use audited deactivate, amend, void, or archive workflows instead."
        className="admin-notice"
      />
      {error && <Alert showIcon type="error" title={error} className="admin-notice" />}
      {success && <Alert showIcon type="success" title={success} className="admin-notice" />}

      <Card className="admin-card">
        {tabs.length ? (
          <Tabs items={tabs} />
        ) : (
          <Text type="secondary">Your account has no administration or audit privileges.</Text>
        )}
      </Card>

      <Modal
        title={`Reset password: ${resettingUser?.username ?? ''}`}
        open={resettingUser !== null}
        onCancel={() => {
          setResettingUser(null)
          setResetPassword('')
        }}
        onOk={() => void resetUserPassword()}
        confirmLoading={saving}
        okText="Reset password"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Alert
            type="warning"
            showIcon
            title="This will revoke the user's active sessions. Share the replacement password through an approved secure channel."
          />
          <Input.Password
            aria-label="Replacement password"
            placeholder="Replacement password (14+ characters)"
            value={resetPassword}
            onChange={(event) => setResetPassword(event.target.value)}
          />
        </Space>
      </Modal>

      <Modal
        title={`Assign roles to ${editingUser?.username ?? ''}`}
        open={editingUser !== null}
        onCancel={() => setEditingUser(null)}
        onOk={() => void saveUserRoles()}
        confirmLoading={saving}
      >
        <Select
          mode="multiple"
          className="modal-full-width"
          aria-label="Assign roles"
          value={editingUserRoleIds}
          onChange={setEditingUserRoleIds}
          options={assignableRoles.map((role) => ({ label: role.name, value: role.id }))}
        />
      </Modal>

      <Modal
        title={`Edit user: ${editingUserProfile?.username ?? ''}`}
        open={editingUserProfile !== null}
        onCancel={() => setEditingUserProfile(null)}
        onOk={() => void saveUserProfile()}
        confirmLoading={saving}
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Edit username"
            value={userProfileForm.username}
            onChange={(event) =>
              setUserProfileForm((current) => ({ ...current, username: event.target.value }))
            }
          />
          <Input
            aria-label="Edit email"
            type="email"
            value={userProfileForm.email}
            onChange={(event) =>
              setUserProfileForm((current) => ({ ...current, email: event.target.value }))
            }
          />
          <Input
            aria-label="Edit department"
            placeholder="Department (optional)"
            value={userProfileForm.department}
            onChange={(event) =>
              setUserProfileForm((current) => ({ ...current, department: event.target.value }))
            }
          />
        </Space>
      </Modal>

      <Modal
        title={`Individual access: ${editingUserOverrides?.username ?? ''}`}
        open={editingUserOverrides !== null}
        width={760}
        onCancel={() => setEditingUserOverrides(null)}
        onOk={() => void saveUserPermissionOverrides()}
        confirmLoading={saving}
        okText="Save individual access"
      >
        <Space orientation="vertical" className="modal-full-width">
          <Alert
            showIcon
            type="info"
            title={`${editingUserOverrides ? roles
              .filter((role) => editingUserOverrides.roles.includes(role.name))
              .reduce((count, role) => count + role.permissions.length, 0) : 0} inherited role grants. Individual denies override role grants; individual grants add access. Clear a selection to inherit role access.`}
          />
          <Text strong>Additional grants</Text>
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            aria-label="Individual permission grants"
            placeholder="Select permissions to grant"
            value={userOverrideGrants}
            onChange={(values: string[]) => {
              setUserOverrideGrants(values)
              setUserOverrideDenies((denied) => denied.filter((key) => !values.includes(key)))
            }}
            options={permissions.map((permission) => ({
              label: `${permission.key} — ${permission.description}`,
              value: permission.key,
            }))}
          />
          <Text strong>Individual denies</Text>
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            aria-label="Individual permission denies"
            placeholder="Select inherited permissions to deny"
            value={userOverrideDenies}
            onChange={(values: string[]) => {
              setUserOverrideDenies(values)
              setUserOverrideGrants((granted) => granted.filter((key) => !values.includes(key)))
            }}
            options={permissions.map((permission) => ({
              label: `${permission.key} — ${permission.description}`,
              value: permission.key,
            }))}
          />
        </Space>
      </Modal>

      <Modal
        title={`Edit role: ${editingRoleDetails?.name ?? ''}`}
        open={editingRoleDetails !== null}
        onCancel={() => setEditingRoleDetails(null)}
        onOk={() => void saveRoleDetails()}
        confirmLoading={saving}
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Role name"
            value={roleDetailsForm.name}
            onChange={(event) =>
              setRoleDetailsForm((current) => ({ ...current, name: event.target.value }))
            }
          />
          <Input
            aria-label="Role description"
            value={roleDetailsForm.description}
            onChange={(event) =>
              setRoleDetailsForm((current) => ({ ...current, description: event.target.value }))
            }
          />
        </Space>
      </Modal>

      <Modal
        title={`Edit privileges: ${editingRole?.name ?? ''}`}
        open={editingRole !== null}
        width={900}
        onCancel={() => setEditingRole(null)}
        onOk={() => void saveRolePermissions()}
        confirmLoading={saving}
        okText="Save privileges"
      >
        <Alert
          type="warning"
          showIcon
          title="Grant only the access required for the role. The SuperAdmin role is reserved and cannot be changed here."
          className="permission-editor-notice"
        />
        <Collapse items={permissionGroups} />
      </Modal>

      <Modal
        title={editingPermission ? `Edit permission: ${editingPermission.key}` : 'Create permission'}
        open={editingPermission !== null}
        onCancel={() => {
          setEditingPermission(null)
          setPermissionForm({ key: '', description: '' })
        }}
        onOk={() => void savePermission()}
        confirmLoading={saving}
      >
        <Space orientation="vertical" className="modal-full-width">
          <Input
            aria-label="Permission key"
            placeholder="custom.permission.action"
            disabled={editingPermission?.is_system}
            value={permissionForm.key}
            onChange={(event) =>
              setPermissionForm((current) => ({ ...current, key: event.target.value }))
            }
          />
          <Input
            aria-label="Permission description"
            placeholder="Permission description"
            value={permissionForm.description}
            onChange={(event) =>
              setPermissionForm((current) => ({ ...current, description: event.target.value }))
            }
          />
        </Space>
      </Modal>
    </div>
  )
}

export default AdminConsole
