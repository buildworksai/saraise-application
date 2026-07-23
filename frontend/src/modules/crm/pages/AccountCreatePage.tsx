import { useState } from 'react';
import { useMutation,useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card,CardContent } from '@/components/ui/Card';
import { CrmPage } from '../components/CrmPage';
import { AccountForm } from '../forms/AccountForm';
import type { DuplicateAccountResult } from '../contracts';
import { CrmApiError,crmKeys,crmService } from '../services/crm-service';
export function AccountCreatePage(){const navigate=useNavigate(),client=useQueryClient();const[duplicates,setDuplicates]=useState<DuplicateAccountResult>();const create=useMutation({mutationFn:crmService.createAccount,onSuccess:async account=>{await client.invalidateQueries({queryKey:crmKeys.all});navigate(`/crm/accounts/${account.id}`)}});const matches=[...(duplicates?.local_matches??[]),...(duplicates?.external_matches??[])];return <CrmPage title="Create account" description="Duplicate review keeps the customer graph clean." parent={{label:'Accounts',to:'/crm/accounts'}}>{matches.length?<aside role="status" className="rounded border border-accent bg-accent/20 p-4"><h2 className="font-semibold">Possible duplicate accounts</h2><ul className="mt-2 list-disc pl-5 text-sm">{matches.map(candidate=><li key={candidate.id}>{candidate.name}{candidate.website?` · ${candidate.website}`:''}</li>)}</ul><p className="mt-2 text-xs">External enrichment: {duplicates?.enrichment_status}</p></aside>:null}<Card><CardContent className="pt-6"><AccountForm pending={create.isPending} serverError={create.error instanceof CrmApiError?create.error.message:null} onCheckDuplicates={(name,website)=>void crmService.findAccountDuplicates(name,website).then(setDuplicates)} onSubmit={async payload=>{await create.mutateAsync(payload)}}/></CardContent></Card></CrmPage>}
