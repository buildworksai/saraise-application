/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Safe HTML rendering with environment awareness
// frontend/src/components/SafeHTML.tsx
// Reference: docs/architecture/security-model.md § 3 (Security Mechanisms)
// CRITICAL NOTES:
// - All HTML content MUST be sanitized via DOMPurify (security-model.md § 3)
// - allowHTML=false: Plain text only, all tags stripped (safest default)
// - Development environment: Allow raw HTML for testing purposes only
// - Staging environment: Standard sanitization (safe tags: p, br, strong, em, lists, links)
// - Production environment: Maximum strict sanitization (only safe text tags, no attributes)
// - URLs in production MUST not include href attributes (no external links in prod)
// - Never use dangerouslySetInnerHTML directly - always use this SafeHTML component
// - User-provided content ALWAYS requires sanitization before rendering
// - Event handlers (onclick, onload) automatically stripped by DOMPurify config
// Source: docs/architecture/security-model.md § 3, OWASP DOMPurify Usage Guide
import React from 'react';
import DOMPurify from 'dompurify';
import { config } from '@/lib/config';
import { xssPrevention } from '@/lib/xss-prevention';

interface SafeHTMLProps {
  content: string;
  allowHTML?: boolean;
  className?: string;
}

export function SafeHTML({ content, allowHTML = false, className }: SafeHTMLProps) {
  const sanitizedContent = React.useMemo(() => {
    if (!allowHTML) {
      return xssPrevention.sanitizeInput(content, 'text');
    }

    // Environment-aware HTML sanitization
    if (config.app.env === 'development') {
      return content; // Allow HTML in development
    } else if (config.app.env === 'staging') {
      return DOMPurify.sanitize(content, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a'],
        ALLOWED_ATTR: ['href', 'target']
      });
    } else {
      // Production: Strict HTML sanitization
      return DOMPurify.sanitize(content, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em'],
        ALLOWED_ATTR: []
      });
    }
  }, [content, allowHTML]);

  return (
    <div
      className={className}
      dangerouslySetInnerHTML={{ __html: sanitizedContent }}
    />
  );
}

