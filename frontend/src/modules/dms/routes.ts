import { lazy } from 'react';
import { FolderTree } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const modes = ['development', 'self-hosted', 'saas'] as const;
const parentRouteId = 'dms.documents.list';
const contextual = { type: 'contextual' as const, parentRouteId };

export const tenantRoutes = [
  { id: parentRouteId, module: 'dms', path: '/dms/documents', sourceFile: 'modules/dms/pages/DocumentBrowserPage.tsx', Page: lazy(() => import('./pages/DocumentBrowserPage').then(({ DocumentBrowserPage }) => ({ default: DocumentBrowserPage }))), modes, navigation: { type: 'sidebar', label: 'Document Management', icon: FolderTree, order: 45 } },
  { id: 'dms.documents.create', module: 'dms', path: '/dms/documents/new', sourceFile: 'modules/dms/pages/UploadDocumentPage.tsx', Page: lazy(() => import('./pages/UploadDocumentPage').then(({ UploadDocumentPage }) => ({ default: UploadDocumentPage }))), modes, navigation: contextual },
  { id: 'dms.documents.detail', module: 'dms', path: '/dms/documents/:id', sourceFile: 'modules/dms/pages/DocumentDetailPage.tsx', Page: lazy(() => import('./pages/DocumentDetailPage').then(({ DocumentDetailPage }) => ({ default: DocumentDetailPage }))), modes, navigation: contextual },
  { id: 'dms.documents.edit', module: 'dms', path: '/dms/documents/:id/edit', sourceFile: 'modules/dms/pages/EditDocumentPage.tsx', Page: lazy(() => import('./pages/EditDocumentPage').then(({ EditDocumentPage }) => ({ default: EditDocumentPage }))), modes, navigation: contextual },
  { id: 'dms.folders.detail', module: 'dms', path: '/dms/folders/:id', sourceFile: 'modules/dms/pages/FolderDetailPage.tsx', Page: lazy(() => import('./pages/FolderDetailPage').then(({ FolderDetailPage }) => ({ default: FolderDetailPage }))), modes, navigation: contextual },
  { id: 'dms.folders.create', module: 'dms', path: '/dms/folders/new', sourceFile: 'modules/dms/pages/CreateFolderPage.tsx', Page: lazy(() => import('./pages/CreateFolderPage').then(({ CreateFolderPage }) => ({ default: CreateFolderPage }))), modes, navigation: contextual },
  { id: 'dms.folders.edit', module: 'dms', path: '/dms/folders/:id/edit', sourceFile: 'modules/dms/pages/EditFolderPage.tsx', Page: lazy(() => import('./pages/EditFolderPage').then(({ EditFolderPage }) => ({ default: EditFolderPage }))), modes, navigation: contextual },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
