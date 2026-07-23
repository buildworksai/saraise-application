import { lazy } from 'react';
import { Briefcase, Building2, CalendarCheck, LayoutDashboard, Pencil, Plus, Settings, TrendingUp, Users } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const pages = {
  SalesDashboardPage: lazy(() => import('./pages/SalesDashboardPage').then(module => ({ default: module.SalesDashboardPage }))),
  LeadListPage: lazy(() => import('./pages/LeadListPage').then(module => ({ default: module.LeadListPage }))), LeadCreatePage: lazy(() => import('./pages/LeadCreatePage').then(module => ({ default: module.LeadCreatePage }))), LeadDetailPage: lazy(() => import('./pages/LeadDetailPage').then(module => ({ default: module.LeadDetailPage }))), LeadEditPage: lazy(() => import('./pages/LeadEditPage').then(module => ({ default: module.LeadEditPage }))),
  AccountListPage: lazy(() => import('./pages/AccountListPage').then(module => ({ default: module.AccountListPage }))), AccountCreatePage: lazy(() => import('./pages/AccountCreatePage').then(module => ({ default: module.AccountCreatePage }))), AccountDetailPage: lazy(() => import('./pages/AccountDetailPage').then(module => ({ default: module.AccountDetailPage }))), AccountEditPage: lazy(() => import('./pages/AccountEditPage').then(module => ({ default: module.AccountEditPage }))),
  ContactListPage: lazy(() => import('./pages/ContactListPage').then(module => ({ default: module.ContactListPage }))), ContactCreatePage: lazy(() => import('./pages/ContactCreatePage').then(module => ({ default: module.ContactCreatePage }))), ContactDetailPage: lazy(() => import('./pages/ContactDetailPage').then(module => ({ default: module.ContactDetailPage }))), ContactEditPage: lazy(() => import('./pages/ContactEditPage').then(module => ({ default: module.ContactEditPage }))),
  OpportunityListPage: lazy(() => import('./pages/OpportunityListPage').then(module => ({ default: module.OpportunityListPage }))), OpportunityCreatePage: lazy(() => import('./pages/OpportunityCreatePage').then(module => ({ default: module.OpportunityCreatePage }))), OpportunityDetailPage: lazy(() => import('./pages/OpportunityDetailPage').then(module => ({ default: module.OpportunityDetailPage }))), OpportunityEditPage: lazy(() => import('./pages/OpportunityEditPage').then(module => ({ default: module.OpportunityEditPage }))), OpportunityKanbanPage: lazy(() => import('./pages/OpportunityKanbanPage').then(module => ({ default: module.OpportunityKanbanPage }))),
  ActivityListPage: lazy(() => import('./pages/ActivityListPage').then(module => ({ default: module.ActivityListPage }))), ActivityCreatePage: lazy(() => import('./pages/ActivityCreatePage').then(module => ({ default: module.ActivityCreatePage }))), ActivityDetailPage: lazy(() => import('./pages/ActivityDetailPage').then(module => ({ default: module.ActivityDetailPage }))), ActivityEditPage: lazy(() => import('./pages/ActivityEditPage').then(module => ({ default: module.ActivityEditPage }))),
  ConfigurationPage: lazy(() => import('./pages/ConfigurationPage').then(module => ({ default: module.ConfigurationPage }))),
} as const;
type PageName = keyof typeof pages;
const navigable = (id:string,path:string,name:PageName,label:string,order:number,stablePath:string,icon:typeof Plus,requiredPermission?:string):TenantRoute=>({id,module:'crm',path,title:`${label} | SARAISE CRM`,sourceFile:`modules/crm/pages/${name}.tsx`,Page:pages[name],...(requiredPermission?{requiredPermission}:{}),navigation:{type:'sidebar',label,icon,order,path:stablePath}});

export const tenantRoutes = [
  navigable('crm.dashboard','/crm/dashboard','SalesDashboardPage','Dashboard',100,'/crm/dashboard',LayoutDashboard),
  navigable('crm.leads.list','/crm/leads','LeadListPage','Leads',110,'/crm/leads',TrendingUp),
  navigable('crm.leads.create','/crm/leads/new','LeadCreatePage','Create lead',111,'/crm/leads/new',Plus), navigable('crm.leads.detail','/crm/leads/:id','LeadDetailPage','Lead details',112,'/crm/leads',TrendingUp), navigable('crm.leads.edit','/crm/leads/:id/edit','LeadEditPage','Edit lead',113,'/crm/leads',Pencil),
  navigable('crm.accounts.list','/crm/accounts','AccountListPage','Accounts',120,'/crm/accounts',Building2),
  navigable('crm.accounts.create','/crm/accounts/new','AccountCreatePage','Create account',121,'/crm/accounts/new',Plus), navigable('crm.accounts.detail','/crm/accounts/:id','AccountDetailPage','Account details',122,'/crm/accounts',Building2), navigable('crm.accounts.edit','/crm/accounts/:id/edit','AccountEditPage','Edit account',123,'/crm/accounts',Pencil),
  navigable('crm.contacts.list','/crm/contacts','ContactListPage','Contacts',130,'/crm/contacts',Users),
  navigable('crm.contacts.create','/crm/contacts/new','ContactCreatePage','Create contact',131,'/crm/contacts/new',Plus), navigable('crm.contacts.detail','/crm/contacts/:id','ContactDetailPage','Contact details',132,'/crm/contacts',Users), navigable('crm.contacts.edit','/crm/contacts/:id/edit','ContactEditPage','Edit contact',133,'/crm/contacts',Pencil),
  navigable('crm.opportunities.list','/crm/opportunities','OpportunityListPage','Opportunities',140,'/crm/opportunities',Briefcase),
  navigable('crm.opportunities.pipeline','/crm/opportunities/pipeline','OpportunityKanbanPage','Pipeline',141,'/crm/opportunities/pipeline',TrendingUp),
  navigable('crm.opportunities.create','/crm/opportunities/new','OpportunityCreatePage','Create opportunity',142,'/crm/opportunities/new',Plus), navigable('crm.opportunities.detail','/crm/opportunities/:id','OpportunityDetailPage','Opportunity details',143,'/crm/opportunities',Briefcase), navigable('crm.opportunities.edit','/crm/opportunities/:id/edit','OpportunityEditPage','Edit opportunity',144,'/crm/opportunities',Pencil),
  navigable('crm.activities.list','/crm/activities','ActivityListPage','Activities',150,'/crm/activities',CalendarCheck),
  navigable('crm.activities.create','/crm/activities/new','ActivityCreatePage','Create activity',151,'/crm/activities/new',Plus), navigable('crm.activities.detail','/crm/activities/:id','ActivityDetailPage','Activity details',152,'/crm/activities',CalendarCheck), navigable('crm.activities.edit','/crm/activities/:id/edit','ActivityEditPage','Edit activity',153,'/crm/activities',Pencil),
  navigable('crm.configuration','/crm/configuration','ConfigurationPage','Configuration',160,'/crm/configuration',Settings,'crm.configuration:read'),
] satisfies readonly TenantRoute[];

export default tenantRoutes;
