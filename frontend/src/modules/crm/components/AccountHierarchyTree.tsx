/**
 * Account Hierarchy Tree Component
 *
 * Displays account hierarchy as a tree structure.
 */
import { useState } from 'react';
import { ChevronRight, ChevronDown, Building2 } from 'lucide-react';
import type { AccountHierarchyNode } from '../contracts';

interface AccountHierarchyTreeProps {
  hierarchy: AccountHierarchyNode;
}

const TreeNode = ({ node, level = 0 }: { node: AccountHierarchyNode; level?: number }) => {
  const [isExpanded, setIsExpanded] = useState(level < 2); // Auto-expand first 2 levels

  const hasChildren = node.children && node.children.length > 0;
  const indent = level * 24;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-2 hover:bg-muted/50 rounded px-2 cursor-pointer"
        style={{ paddingLeft: `${indent}px` }}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )
        ) : (
          <div className="w-4" /> // Spacer for alignment
        )}
        <Building2 className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm font-medium">{node.name}</span>
        {node.account_type && (
          <span className="text-xs text-muted-foreground ml-2 capitalize">
            ({node.account_type})
          </span>
        )}
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <TreeNode key={child.id} node={child} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  );
};

export const AccountHierarchyTree = ({ hierarchy }: AccountHierarchyTreeProps) => {
  return (
    <div className="border rounded-lg p-4 bg-background">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-foreground mb-1">Account Hierarchy</h3>
        <p className="text-xs text-muted-foreground">
          {hierarchy.children && hierarchy.children.length > 0
            ? `${hierarchy.children.length} child account(s)`
            : 'No child accounts'}
        </p>
      </div>
      <div className="space-y-1">
        <TreeNode node={hierarchy} level={0} />
      </div>
    </div>
  );
};
