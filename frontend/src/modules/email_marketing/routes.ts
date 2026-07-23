import { lazy } from 'react';
import {
  ContactRound,
  FilePenLine,
  FilePlus2,
  FileSearch,
  MailCheck,
  Megaphone,
  Settings2,
  ShieldOff,
  SwatchBook,
} from 'lucide-react';
import type { TenantRoute, TenantRouteIcon } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

const modes = ['development', 'self-hosted', 'saas'] as const;
const moduleName = 'email_marketing';
const contextual = (parentRouteId: string, label: string, icon: TenantRouteIcon, order: number) => ({
  type: 'contextual' as const,
  parentRouteId,
  label,
  icon,
  order,
});

export const tenantRoutes = [
  { id: 'email-marketing.campaigns', module: moduleName, path: ROUTES.CAMPAIGNS, title: 'Email campaigns', sourceFile: 'modules/email_marketing/pages/EmailCampaignListPage.tsx', Page: lazy(() => import('./pages/EmailCampaignListPage').then((m) => ({ default: m.EmailCampaignListPage }))), modes, navigation: { type: 'sidebar', label: 'Campaigns', icon: Megaphone, order: 700 } },
  { id: 'email-marketing.campaign-create', module: moduleName, path: ROUTES.CAMPAIGN_CREATE, title: 'Create email campaign', sourceFile: 'modules/email_marketing/pages/CreateEmailCampaignPage.tsx', Page: lazy(() => import('./pages/CreateEmailCampaignPage').then((m) => ({ default: m.CreateEmailCampaignPage }))), modes, navigation: contextual('email-marketing.campaigns', 'Create campaign', FilePlus2, 701) },
  { id: 'email-marketing.campaign-detail', module: moduleName, path: ROUTES.CAMPAIGN_DETAIL(':id'), title: 'Email campaign detail', sourceFile: 'modules/email_marketing/pages/EmailCampaignDetailPage.tsx', Page: lazy(() => import('./pages/EmailCampaignDetailPage').then((m) => ({ default: m.EmailCampaignDetailPage }))), modes, navigation: contextual('email-marketing.campaigns', 'Campaign detail', FileSearch, 702) },
  { id: 'email-marketing.campaign-edit', module: moduleName, path: ROUTES.CAMPAIGN_EDIT(':id'), title: 'Edit email campaign', sourceFile: 'modules/email_marketing/pages/EditEmailCampaignPage.tsx', Page: lazy(() => import('./pages/EditEmailCampaignPage').then((m) => ({ default: m.EditEmailCampaignPage }))), modes, navigation: contextual('email-marketing.campaigns', 'Edit campaign', FilePenLine, 703) },
  { id: 'email-marketing.templates', module: moduleName, path: ROUTES.TEMPLATES, title: 'Email templates', sourceFile: 'modules/email_marketing/pages/EmailTemplateListPage.tsx', Page: lazy(() => import('./pages/EmailTemplateListPage').then((m) => ({ default: m.EmailTemplateListPage }))), modes, navigation: { type: 'sidebar', label: 'Templates', icon: SwatchBook, order: 710 } },
  { id: 'email-marketing.template-create', module: moduleName, path: ROUTES.TEMPLATE_CREATE, title: 'Create email template', sourceFile: 'modules/email_marketing/pages/CreateEmailTemplatePage.tsx', Page: lazy(() => import('./pages/CreateEmailTemplatePage').then((m) => ({ default: m.CreateEmailTemplatePage }))), modes, navigation: contextual('email-marketing.templates', 'Create template', FilePlus2, 711) },
  { id: 'email-marketing.template-detail', module: moduleName, path: ROUTES.TEMPLATE_DETAIL(':id'), title: 'Email template detail', sourceFile: 'modules/email_marketing/pages/EmailTemplateDetailPage.tsx', Page: lazy(() => import('./pages/EmailTemplateDetailPage').then((m) => ({ default: m.EmailTemplateDetailPage }))), modes, navigation: contextual('email-marketing.templates', 'Template detail', FileSearch, 712) },
  { id: 'email-marketing.template-edit', module: moduleName, path: ROUTES.TEMPLATE_EDIT(':id'), title: 'Edit email template', sourceFile: 'modules/email_marketing/pages/EditEmailTemplatePage.tsx', Page: lazy(() => import('./pages/EditEmailTemplatePage').then((m) => ({ default: m.EditEmailTemplatePage }))), modes, navigation: contextual('email-marketing.templates', 'Edit template', FilePenLine, 713) },
  { id: 'email-marketing.delivery', module: moduleName, path: ROUTES.DELIVERY, title: 'Audience and delivery', sourceFile: 'modules/email_marketing/pages/AudienceDeliveryListPage.tsx', Page: lazy(() => import('./pages/AudienceDeliveryListPage').then((m) => ({ default: m.AudienceDeliveryListPage }))), modes, navigation: { type: 'sidebar', label: 'Delivery', icon: MailCheck, order: 720 } },
  { id: 'email-marketing.recipient-detail', module: moduleName, path: ROUTES.RECIPIENT_DETAIL(':id'), title: 'Recipient evidence', sourceFile: 'modules/email_marketing/pages/EmailRecipientDetailPage.tsx', Page: lazy(() => import('./pages/EmailRecipientDetailPage').then((m) => ({ default: m.EmailRecipientDetailPage }))), modes, navigation: contextual('email-marketing.delivery', 'Recipient detail', FileSearch, 721) },
  { id: 'email-marketing.delivery-detail', module: moduleName, path: ROUTES.DELIVERY_DETAIL(':id'), title: 'Delivery attempt evidence', sourceFile: 'modules/email_marketing/pages/EmailDeliveryDetailPage.tsx', Page: lazy(() => import('./pages/EmailDeliveryDetailPage').then((m) => ({ default: m.EmailDeliveryDetailPage }))), modes, navigation: contextual('email-marketing.delivery', 'Delivery detail', FileSearch, 722) },
  { id: 'email-marketing.suppressions', module: moduleName, path: ROUTES.SUPPRESSIONS, title: 'Email suppressions', sourceFile: 'modules/email_marketing/pages/SuppressionListPage.tsx', Page: lazy(() => import('./pages/SuppressionListPage').then((m) => ({ default: m.SuppressionListPage }))), modes, navigation: { type: 'sidebar', label: 'Suppressions', icon: ShieldOff, order: 730 } },
  { id: 'email-marketing.suppression-create', module: moduleName, path: ROUTES.SUPPRESSION_CREATE, title: 'Add email suppression', sourceFile: 'modules/email_marketing/pages/CreateSuppressionPage.tsx', Page: lazy(() => import('./pages/CreateSuppressionPage').then((m) => ({ default: m.CreateSuppressionPage }))), modes, navigation: contextual('email-marketing.suppressions', 'Add suppression', FilePlus2, 731) },
  { id: 'email-marketing.suppression-detail', module: moduleName, path: ROUTES.SUPPRESSION_DETAIL(':id'), title: 'Suppression evidence', sourceFile: 'modules/email_marketing/pages/SuppressionDetailPage.tsx', Page: lazy(() => import('./pages/SuppressionDetailPage').then((m) => ({ default: m.SuppressionDetailPage }))), modes, navigation: contextual('email-marketing.suppressions', 'Suppression detail', FileSearch, 732) },
  { id: 'email-marketing.consents', module: moduleName, path: ROUTES.CONSENTS, title: 'Email consent history', sourceFile: 'modules/email_marketing/pages/ConsentListPage.tsx', Page: lazy(() => import('./pages/ConsentListPage').then((m) => ({ default: m.ConsentListPage }))), modes, navigation: { type: 'sidebar', label: 'Consents', icon: ContactRound, order: 740 } },
  { id: 'email-marketing.consent-create', module: moduleName, path: ROUTES.CONSENT_CREATE, title: 'Record email consent', sourceFile: 'modules/email_marketing/pages/RecordConsentPage.tsx', Page: lazy(() => import('./pages/RecordConsentPage').then((m) => ({ default: m.RecordConsentPage }))), modes, navigation: contextual('email-marketing.consents', 'Record consent', FilePlus2, 741) },
  { id: 'email-marketing.consent-detail', module: moduleName, path: ROUTES.CONSENT_DETAIL(':id'), title: 'Consent evidence', sourceFile: 'modules/email_marketing/pages/ConsentDetailPage.tsx', Page: lazy(() => import('./pages/ConsentDetailPage').then((m) => ({ default: m.ConsentDetailPage }))), modes, navigation: contextual('email-marketing.consents', 'Consent detail', FileSearch, 742) },
  { id: 'email-marketing.configuration', module: moduleName, path: ROUTES.CONFIGURATION, title: 'Email marketing configuration', sourceFile: 'modules/email_marketing/pages/EmailMarketingConfigurationPage.tsx', requiredPermission: 'email_marketing.configuration:read', Page: lazy(() => import('./pages/EmailMarketingConfigurationPage').then((m) => ({ default: m.EmailMarketingConfigurationPage }))), modes, navigation: { type: 'sidebar', label: 'Configuration', icon: Settings2, order: 750 } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
