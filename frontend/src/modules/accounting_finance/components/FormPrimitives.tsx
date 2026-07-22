import type { ReactNode } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

export interface FormErrors { readonly [field: string]: string | undefined }

export function FormGrid({ children }: { children: ReactNode }) { return <div className="grid gap-4 sm:grid-cols-2">{children}</div>; }
export function Field({ id, label, error, required, ...props }: { id: string; label: string; error?: string; required?: boolean } & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'id'>) { return <Input id={id} label={label} error={error} required={required} {...props} />; }
export function SelectField({ id, label, value, onChange, children, error, required }: { id: string; label: string; value: string; onChange: (value: string) => void; children: ReactNode; error?: string; required?: boolean }) { return <div><label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label><select id={id} value={value} onChange={(event) => onChange(event.target.value)} required={required} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} className="h-10 w-full rounded-md border bg-background px-3">{children}</select>{error ? <p id={`${id}-error`} className="mt-1 text-sm text-destructive">{error}</p> : null}</div>; }
export function TextAreaField({ id, label, value, onChange, error }: { id: string; label: string; value: string; onChange: (value: string) => void; error?: string }) { return <div><label htmlFor={id} className="mb-1 block text-sm font-medium">{label}</label><textarea id={id} value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={Boolean(error)} className="min-h-24 w-full rounded-md border bg-background p-3" />{error ? <p className="mt-1 text-sm text-destructive">{error}</p> : null}</div>; }
export function SubmitRow({ pending, submitLabel, onCancel }: { pending: boolean; submitLabel: string; onCancel: () => void }) { return <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={onCancel} disabled={pending}>Cancel</Button><Button type="submit" disabled={pending}>{pending ? 'Saving…' : submitLabel}</Button></div>; }
