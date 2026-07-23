import type { FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import type {
  AttendanceCreate, AttendanceStatus, AttendanceUpdate, DepartmentCreate, DepartmentUpdate,
  EmployeeCreate, EmployeeUpdate, EmploymentType, LeaveBalanceCreate, LeaveBalanceUpdate,
  HumanResourcesConfigurationDocument, LeaveRequestCreate, LeaveRequestUpdate, LeaveType,
} from '../contracts';
import { FormError } from './hr-ui';

export interface Choice { readonly id: string; readonly label: string }
type Errors = Readonly<Record<string, string>>;
interface FormActions { pending: boolean; submitLabel: string; onCancel: () => void }

const control = 'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: React.ReactNode }) {
  return <div><label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>{children}<FormError message={error} /></div>;
}
function Actions({ pending, submitLabel, onCancel }: FormActions) {
  return <div className="flex flex-wrap gap-3 border-t pt-5"><Button type="submit" disabled={pending} className="min-h-11">{pending ? 'Saving…' : submitLabel}</Button><Button type="button" variant="outline" disabled={pending} onClick={onCancel} className="min-h-11">Cancel</Button></div>;
}

export function EmployeeForm({ value, setValue, departments, managers, errors, onSubmit, ...actions }: {
  value: EmployeeCreate | EmployeeUpdate; setValue: (value: EmployeeCreate | EmployeeUpdate) => void;
  departments: readonly Choice[]; managers: readonly Choice[]; configuration: HumanResourcesConfigurationDocument;
  errors: Errors; onSubmit: (event: FormEvent) => void;
} & FormActions) {
  const data = value as EmployeeCreate;
  return <form onSubmit={onSubmit} className="grid gap-5 sm:grid-cols-2" noValidate>
    <Field id="employee-number" label="Employee number" error={errors.employee_number}><Input id="employee-number" required value={data.employee_number ?? ''} onChange={(event) => setValue({ ...value, employee_number: event.target.value })} /></Field>
    <Field id="employee-type" label="Employment type" error={errors.employment_type}><select id="employee-type" className={control} value={data.employment_type ?? actions.configuration.defaults.employment_type} onChange={(event) => setValue({ ...value, employment_type: event.target.value as EmploymentType })}>{actions.configuration.allowed_values.employment_types.map((type) => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></Field>
    <Field id="first-name" label="First name" error={errors.first_name}><Input id="first-name" required value={data.first_name ?? ''} onChange={(event) => setValue({ ...value, first_name: event.target.value })} /></Field>
    <Field id="last-name" label="Last name" error={errors.last_name}><Input id="last-name" required value={data.last_name ?? ''} onChange={(event) => setValue({ ...value, last_name: event.target.value })} /></Field>
    <Field id="employee-email" label="Email" error={errors.email}><Input id="employee-email" type="email" required value={data.email ?? ''} onChange={(event) => setValue({ ...value, email: event.target.value })} /></Field>
    <Field id="employee-phone" label="Phone" error={errors.phone}><Input id="employee-phone" type="tel" value={data.phone ?? ''} onChange={(event) => setValue({ ...value, phone: event.target.value })} /></Field>
    <Field id="employee-department" label="Department" error={errors.department_id}><select id="employee-department" className={control} value={data.department_id ?? ''} onChange={(event) => setValue({ ...value, department_id: event.target.value || null })}><option value="">Unassigned</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
    <Field id="employee-manager" label="Manager" error={errors.manager_id}><select id="employee-manager" className={control} value={data.manager_id ?? ''} onChange={(event) => setValue({ ...value, manager_id: event.target.value || null })}><option value="">No manager</option>{managers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
    <Field id="employee-position" label="Position" error={errors.position}><Input id="employee-position" value={data.position ?? ''} onChange={(event) => setValue({ ...value, position: event.target.value })} /></Field>
    <Field id="employee-hire-date" label="Hire date" error={errors.hire_date}><Input id="employee-hire-date" type="date" required value={data.hire_date ?? ''} onChange={(event) => setValue({ ...value, hire_date: event.target.value })} /></Field>
    <div className="sm:col-span-2"><Actions {...actions} /></div>
  </form>;
}

export function DepartmentForm({ value, setValue, departments, managers, errors, onSubmit, ...actions }: {
  value: DepartmentCreate | DepartmentUpdate; setValue: (value: DepartmentCreate | DepartmentUpdate) => void;
  departments: readonly Choice[]; managers: readonly Choice[]; configuration: HumanResourcesConfigurationDocument;
  errors: Errors; onSubmit: (event: FormEvent) => void;
} & FormActions) {
  return <form onSubmit={onSubmit} className="grid gap-5 sm:grid-cols-2" noValidate>
    <Field id="department-code" label="Department code" error={errors.department_code}><Input id="department-code" required value={value.department_code ?? ''} onChange={(event) => setValue({ ...value, department_code: event.target.value })} /></Field>
    <Field id="department-name" label="Department name" error={errors.department_name}><Input id="department-name" required value={value.department_name ?? ''} onChange={(event) => setValue({ ...value, department_name: event.target.value })} /></Field>
    <Field id="parent-department" label="Parent department" error={errors.parent_department_id}><select id="parent-department" className={control} value={value.parent_department_id ?? ''} onChange={(event) => setValue({ ...value, parent_department_id: event.target.value || null })}><option value="">Top level</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
    <Field id="department-manager" label="Manager" error={errors.manager_id}><select id="department-manager" className={control} value={value.manager_id ?? ''} onChange={(event) => setValue({ ...value, manager_id: event.target.value || null })}><option value="">No manager</option>{managers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
    <div className="sm:col-span-2"><Field id="department-description" label="Description" error={errors.description}><Textarea id="department-description" value={value.description ?? ''} onChange={(event) => setValue({ ...value, description: event.target.value })} /></Field></div>
    <div className="sm:col-span-2"><Actions {...actions} /></div>
  </form>;
}

export function AttendanceForm({ value, setValue, employees, errors, onSubmit, editing = false, ...actions }: {
  value: AttendanceCreate | AttendanceUpdate; setValue: (value: AttendanceCreate | AttendanceUpdate) => void;
  employees: readonly Choice[]; configuration: HumanResourcesConfigurationDocument;
  errors: Errors; onSubmit: (event: FormEvent) => void; editing?: boolean;
} & FormActions) {
  const data = value as AttendanceCreate & AttendanceUpdate;
  return <form onSubmit={onSubmit} className="grid gap-5 sm:grid-cols-2" noValidate>
    {!editing ? <Field id="attendance-employee" label="Employee" error={errors.employee_id}><select required id="attendance-employee" className={control} value={data.employee_id ?? ''} onChange={(event) => setValue({ ...value, employee_id: event.target.value } as AttendanceCreate)}><option value="">Select employee</option>{employees.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field> : null}
    {!editing ? <Field id="attendance-date" label="Attendance date" error={errors.attendance_date}><Input required id="attendance-date" type="date" value={data.attendance_date ?? ''} onChange={(event) => setValue({ ...value, attendance_date: event.target.value } as AttendanceCreate)} /></Field> : null}
    <Field id="attendance-status" label="Status" error={errors.status}><select id="attendance-status" className={control} value={data.status ?? actions.configuration.defaults.attendance_status} onChange={(event) => setValue({ ...value, status: event.target.value as AttendanceStatus })}>{actions.configuration.allowed_values.attendance_statuses.map((status) => <option key={status}>{status}</option>)}</select></Field>
    <Field id="check-in" label="Check-in time" error={errors.check_in_time}><Input id="check-in" type="datetime-local" value={data.check_in_time?.slice(0, 16) ?? ''} onChange={(event) => setValue({ ...value, check_in_time: event.target.value ? new Date(event.target.value).toISOString() : null })} /></Field>
    <Field id="check-out" label="Check-out time" error={errors.check_out_time}><Input id="check-out" type="datetime-local" value={data.check_out_time?.slice(0, 16) ?? ''} onChange={(event) => setValue({ ...value, check_out_time: event.target.value ? new Date(event.target.value).toISOString() : null })} /></Field>
    <div className="sm:col-span-2"><Field id="attendance-notes" label={editing ? 'Correction note (required)' : 'Notes'} error={errors.notes}><Textarea required={editing} id="attendance-notes" value={data.notes ?? ''} onChange={(event) => setValue({ ...value, notes: event.target.value })} /></Field></div>
    <div className="sm:col-span-2"><Actions {...actions} /></div>
  </form>;
}

export function LeaveBalanceForm({ value, setValue, employees, errors, onSubmit, editing = false, ...actions }: {
  value: LeaveBalanceCreate | LeaveBalanceUpdate; setValue: (value: LeaveBalanceCreate | LeaveBalanceUpdate) => void;
  employees: readonly Choice[]; configuration: HumanResourcesConfigurationDocument;
  errors: Errors; onSubmit: (event: FormEvent) => void; editing?: boolean;
} & FormActions) {
  const data = value as LeaveBalanceCreate & LeaveBalanceUpdate;
  return <form onSubmit={onSubmit} className="grid gap-5 sm:grid-cols-2" noValidate>
    {!editing ? <><Field id="balance-employee" label="Employee" error={errors.employee_id}><select required id="balance-employee" className={control} value={data.employee_id ?? ''} onChange={(event) => setValue({ ...value, employee_id: event.target.value } as LeaveBalanceCreate)}><option value="">Select employee</option>{employees.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
      <Field id="leave-type" label="Leave type" error={errors.leave_type}><select id="leave-type" className={control} value={data.leave_type ?? actions.configuration.defaults.leave_type} onChange={(event) => setValue({ ...value, leave_type: event.target.value as LeaveType } as LeaveBalanceCreate)}>{actions.configuration.allowed_values.leave_types.map((type) => <option key={type}>{type}</option>)}</select></Field>
      <Field id="period-start" label="Period start" error={errors.period_start}><Input required id="period-start" type="date" value={data.period_start ?? ''} onChange={(event) => setValue({ ...value, period_start: event.target.value } as LeaveBalanceCreate)} /></Field>
      <Field id="period-end" label="Period end" error={errors.period_end}><Input required id="period-end" type="date" value={data.period_end ?? ''} onChange={(event) => setValue({ ...value, period_end: event.target.value } as LeaveBalanceCreate)} /></Field></> : null}
    <Field id="entitled-days" label="Entitled days" error={errors.entitled_days}><Input required id="entitled-days" type="number" min={actions.configuration.limits.leave_input_minimum} step={actions.configuration.limits.leave_input_step} value={data.entitled_days ?? actions.configuration.defaults.leave_entitled_days} onChange={(event) => setValue({ ...value, entitled_days: event.target.value })} /></Field>
    <Field id="carried-days" label="Carried days" error={errors.carried_days}><Input required id="carried-days" type="number" min={actions.configuration.limits.leave_input_minimum} step={actions.configuration.limits.leave_input_step} value={data.carried_days ?? actions.configuration.defaults.leave_carried_days} onChange={(event) => setValue({ ...value, carried_days: event.target.value })} /></Field>
    {editing ? <div className="sm:col-span-2"><Field id="adjustment-note" label="Adjustment note" error={errors.note}><Textarea required id="adjustment-note" value={data.note ?? ''} onChange={(event) => setValue({ ...value, note: event.target.value } as LeaveBalanceUpdate)} /></Field></div> : null}
    <div className="sm:col-span-2"><Actions {...actions} /></div>
  </form>;
}

export function LeaveRequestForm({ value, setValue, employees, balances, errors, onSubmit, editing = false, ...actions }: {
  value: LeaveRequestCreate | LeaveRequestUpdate; setValue: (value: LeaveRequestCreate | LeaveRequestUpdate) => void;
  employees: readonly Choice[]; balances: readonly Choice[]; configuration: HumanResourcesConfigurationDocument;
  errors: Errors; onSubmit: (event: FormEvent) => void; editing?: boolean;
} & FormActions) {
  const data = value as LeaveRequestCreate;
  return <form onSubmit={onSubmit} className="grid gap-5 sm:grid-cols-2" noValidate>
    {!editing ? <><Field id="request-employee" label="Employee" error={errors.employee_id}><select required id="request-employee" className={control} value={data.employee_id ?? ''} onChange={(event) => setValue({ ...value, employee_id: event.target.value } as LeaveRequestCreate)}><option value="">Select employee</option>{employees.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
      <Field id="request-balance" label="Leave allocation" error={errors.leave_balance_id}><select required id="request-balance" className={control} value={data.leave_balance_id ?? ''} onChange={(event) => setValue({ ...value, leave_balance_id: event.target.value } as LeaveRequestCreate)}><option value="">Select allocation</option>{balances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></Field>
      <Field id="request-type" label="Leave type" error={errors.leave_type}><select id="request-type" className={control} value={data.leave_type ?? actions.configuration.defaults.leave_type} onChange={(event) => setValue({ ...value, leave_type: event.target.value as LeaveType } as LeaveRequestCreate)}>{actions.configuration.allowed_values.leave_types.map((type) => <option key={type}>{type}</option>)}</select></Field></> : null}
    <Field id="request-start" label="Start date" error={errors.start_date}><Input required id="request-start" type="date" value={data.start_date ?? ''} onChange={(event) => setValue({ ...value, start_date: event.target.value })} /></Field>
    <Field id="request-end" label="End date" error={errors.end_date}><Input required id="request-end" type="date" value={data.end_date ?? ''} onChange={(event) => setValue({ ...value, end_date: event.target.value })} /></Field>
    <div className="sm:col-span-2"><Field id="request-reason" label="Reason" error={errors.reason}><Textarea id="request-reason" value={data.reason ?? ''} onChange={(event) => setValue({ ...value, reason: event.target.value })} /></Field></div>
    <div className="sm:col-span-2"><Actions {...actions} /></div>
  </form>;
}
