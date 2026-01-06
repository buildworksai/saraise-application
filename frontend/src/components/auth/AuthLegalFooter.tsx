/**
 * SPDX-License-Identifier: Apache-2.0
 */

import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

const legalLinks = [
  { label: 'Terms of Service', href: '/legal/terms' },
  { label: 'Privacy Policy', href: '/legal/privacy' },
  { label: 'Security', href: '/security' },
  { label: 'Support', href: '/support' },
]

interface AuthLegalFooterProps {
  className?: string
}

export function AuthLegalFooter({ className }: AuthLegalFooterProps) {
  return (
    <div className={cn('text-center border-t border-gray-200 dark:border-gray-700 pt-6 mt-6', className)}>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        SARAISE - Secure and Reliable AI Symphony ERP
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-4 text-xs text-muted-foreground">
        {legalLinks.map((link) => (
          <Link
            key={link.label}
            to={link.href}
            className="hover:text-primary-main transition-colors"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  )
}

