import { lazy } from 'react';
import { FilePenLine, FilePlus2, FileText, FolderCog, FolderPlus, FolderTree, Settings2 } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const modes = ['development', 'self-hosted', 'saas'] as const;
const parentRouteId = 'dms.documents.list';
const contextual = (label: string, icon: typeof FolderTree, order: number) => ({ type: 'contextual' as const, parentRouteId, label, icon, order });

export const tenantRoutes = [
  { id: parentRouteId, module: 'dms', path: '/dms/documents', title: 'Documents', sourceFile: 'modules/dms/pages/DocumentBrowserPage.tsx', Page: lazy(() => import('./pages/DocumentBrowserPage').then(({ DocumentBrowserPage }) => ({ default: DocumentBrowserPage }))), modes, navigation: { type: 'sidebar', label: 'Documents', icon: FolderTree, order: 45 } },
  { id: 'dms.documents.create', module: 'dms', path: '/dms/documents/new', title: 'Upload document', sourceFile: 'modules/dms/pages/UploadDocumentPage.tsx', Page: lazy(() => import('./pages/UploadDocumentPage').then(({ UploadDocumentPage }) => ({ default: UploadDocumentPage }))), modes, navigation: contextual('Upload document', FilePlus2, 45.01) },
  { id: 'dms.documents.detail', module: 'dms', path: '/dms/documents/:id', title: 'Document details', sourceFile: 'modules/dms/pages/DocumentDetailPage.tsx', Page: lazy(() => import('./pages/DocumentDetailPage').then(({ DocumentDetailPage }) => ({ default: DocumentDetailPage }))), modes, navigation: contextual('Document details', FileText, 45.02) },
  { id: 'dms.documents.edit', module: 'dms', path: '/dms/documents/:id/edit', title: 'Edit document', sourceFile: 'modules/dms/pages/EditDocumentPage.tsx', Page: lazy(() => import('./pages/EditDocumentPage').then(({ EditDocumentPage }) => ({ default: EditDocumentPage }))), modes, navigation: contextual('Edit document', FilePenLine, 45.03) },
  { id: 'dms.folders.detail', module: 'dms', path: '/dms/folders/:id', title: 'Folder details', sourceFile: 'modules/dms/pages/FolderDetailPage.tsx', Page: lazy(() => import('./pages/FolderDetailPage').then(({ FolderDetailPage }) => ({ default: FolderDetailPage }))), modes, navigation: contextual('Folder details', FolderTree, 45.04) },
  { id: 'dms.folders.create', module: 'dms', path: '/dms/folders/new', title: 'Create folder', sourceFile: 'modules/dms/pages/CreateFolderPage.tsx', Page: lazy(() => import('./pages/CreateFolderPage').then(({ CreateFolderPage }) => ({ default: CreateFolderPage }))), modes, navigation: contextual('Create folder', FolderPlus, 45.05) },
  { id: 'dms.folders.edit', module: 'dms', path: '/dms/folders/:id/edit', title: 'Edit folder', sourceFile: 'modules/dms/pages/EditFolderPage.tsx', Page: lazy(() => import('./pages/EditFolderPage').then(({ EditFolderPage }) => ({ default: EditFolderPage }))), modes, navigation: contextual('Edit folder', FolderCog, 45.06) },
  { id: 'dms.configuration', module: 'dms', path: '/dms/configuration', title: 'DMS configuration', requiredPermission: 'dms.configuration:read', sourceFile: 'modules/dms/pages/DmsConfigurationPage.tsx', Page: lazy(() => import('./pages/DmsConfigurationPage').then(({ DmsConfigurationPage }) => ({ default: DmsConfigurationPage }))), modes, navigation: { type: 'sidebar', label: 'Configuration', icon: Settings2, order: 45.1 } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
