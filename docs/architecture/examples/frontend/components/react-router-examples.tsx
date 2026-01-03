/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: React Router usage examples
// frontend/src/components/example.tsx
// Reference: docs/architecture/application-architecture.md § 5 (Frontend Routing)
// CRITICAL NOTES:
// - Use React Router v6 hooks (useNavigate, useParams, useLocation, useSearchParams)
// - Client-side navigation via useNavigate() - never use window.location
// - Route protection via ProtectedPage component wrapper (server auth decision)
// - Dynamic routes with :id parameter accessed via useParams()
// - Query parameters accessed via useSearchParams() hook
// - Session cookie included automatically via apiClient (credentials: 'include')
// - All external navigation must validate URL (no open redirects)
// - Deep linking supported - React Router maintains browser back/forward compatibility
// - Module-based route structure in frontend/src/modules/{module_name}/pages/
// Source: docs/architecture/application-architecture.md § 5

// ✅ CORRECT Imports:
import { useNavigate, useParams, useLocation } from 'react-router-dom'

// ❌ FORBIDDEN Imports:
// No forbidden imports - use React Router DOM only

// ❌ FORBIDDEN Directives:
// No forbidden directives - Vite/React components are client-side by default

// ✅ CORRECT Navigation:
const navigate = useNavigate()
navigate('/path')  // React Router

// ❌ FORBIDDEN Navigation:
// No forbidden navigation patterns - use React Router only

