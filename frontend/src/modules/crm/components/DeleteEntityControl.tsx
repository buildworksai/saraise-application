import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { GovernedError } from './CrmPage';

export function DeleteEntityControl({label,impact,onDelete,onDeleted}:{label:string;impact:string;onDelete:()=>Promise<void>;onDeleted:()=>void}){
  const[open,setOpen]=useState(false);
  const deletion=useMutation({mutationFn:onDelete,onSuccess:()=>{setOpen(false);onDeleted()}});
  return <><Button variant="danger" onClick={()=>setOpen(true)}>Delete</Button><Dialog open={open} onOpenChange={setOpen} title={`Delete this ${label}?`} description={impact}><p className="rounded bg-muted p-3 text-sm">Recovery: cancel now to preserve the record. If deletion is rejected, the record remains active and the server error below explains how to recover.</p>{deletion.error?<GovernedError error={deletion.error} onRetry={()=>deletion.mutate()} subject={`${label} deletion`}/>:null}<div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={()=>setOpen(false)}>Cancel</Button><Button variant="danger" disabled={deletion.isPending} onClick={()=>deletion.mutate()}>{deletion.isPending?'Deleting…':'Confirm delete'}</Button></div></Dialog></>;
}
