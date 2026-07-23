import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { GovernedError, SalesPage, newIdempotencyKey, useUnsavedChanges } from './SalesUi';
import { SALES_PATHS, type Customer, type CustomerCreate } from '../contracts';
import { salesQueryKeys, salesService } from '../services/sales-service';

export function CustomerForm({ customer }: { customer?: Customer }) {
  const navigate=useNavigate(); const queryClient=useQueryClient();
  const initial:CustomerCreate={customer_code:customer?.customer_code??'',customer_name:customer?.customer_name??'',email:customer?.email??'',phone:customer?.phone??'',address:customer?.address??'',credit_limit:customer?.credit_limit??null,currency:customer?.currency??'USD',is_active:customer?.is_active??true};
  const [form,setForm]=useState(initial); const [submitted,setSubmitted]=useState(false); const dirty=JSON.stringify(form)!==JSON.stringify(initial);
  useUnsavedChanges(dirty&&!submitted);
  const errors:Record<string,string>={}; if(!form.customer_code.trim())errors.customer_code='Customer code is required.'; if(!form.customer_name.trim())errors.customer_name='Customer name is required.'; if(!/^[A-Z]{3}$/.test(form.currency))errors.currency='Use a three-letter uppercase currency code.'; if(form.credit_limit!==null&&form.credit_limit!==undefined&&form.credit_limit!==''&&Number(form.credit_limit)<0)errors.credit_limit='Credit limit cannot be negative.';
  const mutation=useMutation({mutationFn:()=>customer?salesService.updateCustomer(customer.id,{...form,expected_version:customer.lock_version}):salesService.createCustomer(form,newIdempotencyKey()),onSuccess:(saved)=>{setSubmitted(true);void queryClient.invalidateQueries({queryKey:salesQueryKeys.all});toast.success(customer?'Customer updated':'Customer created');navigate(`${SALES_PATHS.CUSTOMERS}/${encodeURIComponent(saved.id)}`);}});
  const change=<K extends keyof CustomerCreate>(key:K,value:CustomerCreate[K])=>setForm((current)=>({...current,[key]:value}));
  return <SalesPage title={customer?'Edit customer':'Create customer'} description="Maintain a tenant-owned sales profile. Server validation remains authoritative."><Card className="max-w-3xl"><CardHeader><CardTitle>Customer details</CardTitle></CardHeader><CardContent>{mutation.error&&<GovernedError error={mutation.error}/>}<form className="grid gap-5 sm:grid-cols-2" onSubmit={(event)=>{event.preventDefault();if(Object.keys(errors).length===0&&!mutation.isPending)mutation.mutate();}} noValidate>
    <Input id="customer-code" label="Customer code" value={form.customer_code} onChange={(e)=>change('customer_code',e.target.value)} error={errors.customer_code} aria-describedby={errors.customer_code?'customer-code-error':'customer-code-help'} required/><p id="customer-code-help" className="sr-only">A unique code within this tenant.</p>
    <Input id="customer-name" label="Customer name" value={form.customer_name} onChange={(e)=>change('customer_name',e.target.value)} error={errors.customer_name} required/>
    <Input id="email" label="Email" type="email" value={form.email??''} onChange={(e)=>change('email',e.target.value)}/><Input id="phone" label="Phone" value={form.phone??''} onChange={(e)=>change('phone',e.target.value)}/>
    <Input id="currency" label="Currency" maxLength={3} value={form.currency} onChange={(e)=>change('currency',e.target.value.toUpperCase())} error={errors.currency} aria-describedby="currency-help" required/><p id="currency-help" className="sr-only">ISO 4217 currency code, for example USD.</p>
    <Input id="credit-limit" label="Credit limit" inputMode="decimal" min="0" value={form.credit_limit??''} onChange={(e)=>change('credit_limit',e.target.value||null)} error={errors.credit_limit}/>
    <div className="sm:col-span-2"><Textarea id="address" label="Address" value={form.address??''} onChange={(e)=>change('address',e.target.value)} rows={4}/></div>
    <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={form.is_active??true} onChange={(e)=>change('is_active',e.target.checked)} className="h-4 w-4 rounded border-input"/>Active customer</label>
    <div role="status" aria-live="polite" className="sm:col-span-2 flex flex-wrap gap-3"><Button type="submit" disabled={mutation.isPending||Object.keys(errors).length>0}>{mutation.isPending?'Saving…':customer?'Save changes':'Create customer'}</Button><Button type="button" variant="outline" onClick={()=>{if(!dirty||window.confirm('Discard unsaved changes?'))navigate(SALES_PATHS.CUSTOMERS);}}>Cancel</Button></div>
  </form></CardContent></Card></SalesPage>;
}
