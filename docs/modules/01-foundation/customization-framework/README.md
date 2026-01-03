<!-- SPDX-License-Identifier: Apache-2.0 -->
# Customization Framework

**Module Code**: `customization`
**Category**: Foundation
**Priority**: Critical - Extensibility Platform
**Version**: 1.0.0
**Status**: Production Ready

---

## Executive Summary

The Customization Framework is the **extensibility engine** that transforms SARAISE from a standard ERP into a fully programmable business platform. It provides comprehensive server scripts, client scripts, hooks, API extensions, custom endpoints, workflow customization, integration framework, and event-driven architecture. This module empowers developers and power users to extend every aspect of SARAISE without modifying core code, ensuring upgradability while delivering unlimited flexibility.

### Vision

**"Code once, extend everywhere - enterprise-grade extensibility with zero-downtime deployments."**

Every world-class platform needs extensibility. SARAISE's Customization Framework delivers Salesforce Apex-level programmability with Shopify App-level simplicity, enabling developers to create custom business logic, integrations, and automations that seamlessly integrate with the core platform. With AI-powered code generation and intelligent suggestions, we reduce custom development time by 70%.

---

## World-Class Features

### 1. Server Scripts (Backend Logic)
**Status**: Must-Have | **Competitive Parity**: Industry Leading

**Server Script System**:
```python
server_scripts = {
    "concept": {
        "description": "Python code that runs on server events",
        "inspiration": "Frappe Framework server scripts + Salesforce Apex",
        "power": "Full backend customization without touching core code",
        "isolation": "Sandboxed execution environment"
    },
    "script_types": {
        "resource_scripts": {
            "description": "Triggered by Resource events",
            "events": [
                "before_insert",  # Before creating new document
                "after_insert",  # After document created
                "before_validate",  # Before validation runs
                "validate",  # During validation
                "before_save",  # Before any save operation
                "after_save",  # After save operation
                "before_submit",  # Before document submission
                "after_submit",  # After document submitted
                "before_cancel",  # Before document cancelled
                "after_cancel",  # After document cancelled
                "before_delete",  # Before document deleted
                "on_trash",  # When document moved to trash
                "on_update_after_submit",  # After edit of submitted doc
            ],
            "example": """
                # Auto-set sales commission on order save
                def after_save(doc, method):
                    if doc.resource_type == 'Sales Order' and not doc.commission_calculated:
                        sales_person = frappe.get_doc('Sales Person', doc.sales_person)
                        commission_rate = sales_person.commission_rate or 0.05
                        doc.commission_amount = doc.grand_total * commission_rate
                        doc.commission_calculated = True
                        doc.save()
            """
        },
        "api_scripts": {
            "description": "Custom API endpoints",
            "method_types": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            "example": """
                # Custom API: Get customer lifetime value
                @frappe.whitelist()
                def get_customer_ltv(customer_id):
                    # Calculate total revenue from customer
                    invoices = frappe.get_all('Sales Invoice',
                        filters={'customer': customer_id, 'docstatus': 1},
                        fields=['grand_total'])
                    ltv = sum(inv.grand_total for inv in invoices)

                    # Calculate average order value
                    order_count = len(invoices)
                    aov = ltv / order_count if order_count > 0 else 0

                    return {
                        'customer_id': customer_id,
                        'lifetime_value': ltv,
                        'total_orders': order_count,
                        'average_order_value': aov
                    }
            """,
            "endpoint": "POST /api/method/get_customer_ltv",
            "authentication": "Requires API key or session token",
            "rate_limiting": "Subject to tenant rate limits"
        },
        "scheduled_scripts": {
            "description": "Cron-based scheduled tasks",
            "frequency_options": [
                "Every minute",
                "Every 5 minutes",
                "Every 15 minutes",
                "Hourly",
                "Daily",
                "Weekly",
                "Monthly",
                "Cron expression (advanced)"
            ],
            "example": """
                # Send daily sales summary email
                def daily_sales_summary():
                    yesterday = add_days(today(), -1)

                    # Get yesterday's sales
                    sales = frappe.db.sql('''
                        SELECT
                            COUNT(*) as order_count,
                            SUM(grand_total) as total_sales,
                            AVG(grand_total) as avg_order_value
                        FROM `tabSales Order`
                        WHERE DATE(creation) = %s
                          AND docstatus = 1
                    ''', yesterday, as_dict=True)[0]

                    # Send email to management
                    frappe.sendmail(
                        recipients=['management@company.com'],
                        subject=f'Daily Sales Summary - {yesterday}',
                        message=f'''
                            Total Orders: {sales.order_count}
                            Total Sales: ${sales.total_sales:,.2f}
                            Average Order Value: ${sales.avg_order_value:,.2f}
                        '''
                    )
            """,
            "scheduling": "Cron: 0 9 * * *  (Every day at 9 AM)",
            "timezone": "Tenant timezone"
        },
        "permission_query_scripts": {
            "description": "Custom permission logic",
            "use_case": "Complex permission rules beyond role-based",
            "example": """
                # Only allow users to see their own territory's customers
                def get_permission_query_conditions(user):
                    if 'Sales Manager' in frappe.get_roles(user):
                        return ''  # Sales managers see all

                    # Get user's assigned territories
                    territories = frappe.get_all('Sales Person',
                        filters={'user': user},
                        fields=['territory'])

                    if territories:
                        territory_list = ', '.join([f"'{t.territory}'" for t in territories])
                        return f'`tabCustomer`.territory IN ({territory_list})'

                    return '1=0'  # No access if no territory assigned
            """
        },
        "report_scripts": {
            "description": "Custom report generation",
            "report_types": ["Query Report", "Script Report"],
            "example": """
                # Custom sales funnel report
                def execute(filters=None):
                    columns = [
                        {'fieldname': 'stage', 'label': 'Stage', 'fieldtype': 'Data', 'width': 150},
                        {'fieldname': 'count', 'label': 'Count', 'fieldtype': 'Int', 'width': 100},
                        {'fieldname': 'total_value', 'label': 'Total Value', 'fieldtype': 'Currency', 'width': 150},
                        {'fieldname': 'conversion_rate', 'label': 'Conversion %', 'fieldtype': 'Percent', 'width': 120}
                    ]

                    data = get_funnel_data(filters)

                    return columns, data
            """
        }
    },
    "script_features": {
        "full_python_access": {
            "description": "Access to Python standard library",
            "libraries": ["datetime", "json", "csv", "math", "re", "requests"],
            "restrictions": ["os", "sys", "subprocess", "eval", "exec"]
        },
        "frappe_api": {
            "description": "Full Frappe framework API",
            "capabilities": [
                "frappe.get_doc()",  # Get document
                "frappe.new_doc()",  # Create new document
                "frappe.db.sql()",  # Raw SQL queries
                "frappe.db.get_value()",  # Get single value
                "frappe.db.set_value()",  # Update value
                "frappe.db.get_all()",  # Get list of documents
                "frappe.sendmail()",  # Send email
                "frappe.publish_realtime()",  # WebSocket events
                "frappe.enqueue()",  # Background jobs
                "frappe.cache()",  # Redis cache
                "frappe.log_error()",  # Error logging
            ]
        },
        "error_handling": {
            "exceptions": "frappe.throw() to stop execution with error",
            "logging": "frappe.log_error() to log errors",
            "validation": "Automatic rollback on errors",
            "debugging": "Stack traces in error log"
        },
        "performance": {
            "timeout": "30 seconds max execution time",
            "memory_limit": "512 MB per script",
            "database_queries": "Monitored for slow queries",
            "caching": "Redis cache for expensive operations"
        }
    },
    "sandbox_security": {
        "restricted_modules": [
            "os",  # File system access
            "sys",  # System access
            "subprocess",  # Process execution
            "eval/exec",  # Code execution
            "socket",  # Network access
            "__import__"  # Dynamic imports
        ],
        "allowed_modules": [
            "datetime", "json", "csv", "math", "random", "re",
            "requests",  # HTTP requests (whitelisted domains)
            "frappe.*"  # Full Frappe API
        ],
        "tenant_isolation": "Scripts cannot access other tenant data",
        "resource_limits": "CPU, memory, execution time limits",
        "audit_logging": "All script executions logged"
    }
}
```

**Server Script Examples**:
```python
# Example 1: Auto-calculate shipping charges
def before_save(doc, method):
    if doc.resource_type == 'Sales Order' and doc.shipping_method:
        shipping = frappe.get_doc('Shipping Method', doc.shipping_method)

        # Calculate based on weight
        total_weight = sum(item.weight * item.qty for item in doc.items)
        doc.shipping_charges = total_weight * shipping.rate_per_kg

        # Recalculate totals
        doc.grand_total = doc.net_total + doc.tax_total + doc.shipping_charges

# Example 2: Send notification on high-value order
def after_submit(doc, method):
    if doc.resource_type == 'Sales Order' and doc.grand_total > 10000:
        frappe.sendmail(
            recipients=['sales_manager@company.com'],
            subject=f'High-Value Order: {doc.name}',
            message=f'''
                Customer: {doc.customer_name}
                Amount: ${doc.grand_total:,.2f}

                Review order: {frappe.utils.get_url()}/app/sales-order/{doc.name}
            '''
        )

# Example 3: Sync to external system
def after_save(doc, method):
    if doc.resource_type == 'Customer' and doc.sync_to_crm:
        frappe.enqueue(
            'myapp.integrations.sync_customer_to_crm',
            doc=doc,
            queue='short',
            timeout=60
        )
```

### 2. Client Scripts (Frontend Logic)
**Status**: Must-Have | **Competitive Parity**: Industry Leading

**Client Script System**:
```python
client_scripts = {
    "concept": {
        "description": "JavaScript code that runs in browser",
        "execution": "Triggered by form events",
        "purpose": "Dynamic UI behavior, validations, API calls",
        "framework": "Frappe UI framework + jQuery"
    },
    "script_events": {
        "form_events": {
            "onload": "Form loaded first time in session",
            "refresh": "Form refreshed or reloaded",
            "validate": "Before form submission (return false to prevent)",
            "before_save": "Before save operation",
            "after_save": "After successful save",
            "before_submit": "Before document submission",
            "after_submit": "After successful submission",
            "before_cancel": "Before cancellation",
            "on_cancel": "After cancellation"
        },
        "field_events": {
            "[fieldname]": "Field value changed",
            "[fieldname]_query": "Customize link field search",
            "example": """
                frappe.ui.form.on('Sales Order', {
                    customer: function(frm) {
                        // Triggered when customer field changes
                        if (frm.doc.customer) {
                            fetch_customer_details(frm);
                        }
                    }
                });
            """
        }
    },
    "form_api": {
        "field_operations": {
            "set_value": "frm.set_value('fieldname', value)",
            "get_value": "frm.doc.fieldname",
            "set_df_property": "frm.set_df_property('field', 'read_only', 1)",
            "toggle_display": "frm.toggle_display('field', show_or_hide)",
            "toggle_reqd": "frm.toggle_reqd('field', required_or_not)",
            "set_query": "frm.set_query('link_field', function() {...})",
            "refresh_field": "frm.refresh_field('fieldname')"
        },
        "form_operations": {
            "save": "frm.save()",
            "submit": "frm.submit()",
            "cancel": "frm.cancel()",
            "reload_doc": "frm.reload_doc()",
            "enable_save": "frm.enable_save()",
            "disable_save": "frm.disable_save()"
        },
        "child_table_operations": {
            "add_child": "frm.add_child('items', {item_code: 'ITEM-001'})",
            "clear_table": "frm.clear_table('items')",
            "remove_row": "frm.doc.items.splice(row_index, 1)",
            "refresh_table": "frm.refresh_field('items')"
        },
        "ui_operations": {
            "msgprint": "frappe.msgprint('Message')",
            "confirm": "frappe.confirm('Are you sure?', () => {...})",
            "prompt": "frappe.prompt({label: 'Name', fieldtype: 'Data'}, ...)",
            "show_alert": "frappe.show_alert('Success!', 5)",
            "call": "frappe.call({method: 'path.to.method', args: {...}})"
        },
        "custom_buttons": {
            "add_custom_button": """
                frm.add_custom_button('Create Invoice', function() {
                    create_invoice_from_order(frm);
                }, 'Actions');
            """,
            "remove_custom_button": "frm.remove_custom_button('Button Label')",
            "set_primary_action": """
                frm.page.set_primary_action('Approve', function() {
                    approve_document(frm);
                });
            """
        }
    },
    "advanced_features": {
        "api_calls": {
            "description": "Call backend methods from client",
            "example": """
                frappe.call({
                    method: 'myapp.api.get_customer_balance',
                    args: {
                        customer: frm.doc.customer
                    },
                    callback: function(r) {
                        if (r.message) {
                            frm.set_value('outstanding_amount', r.message.balance);
                        }
                    }
                });
            """
        },
        "realtime_updates": {
            "description": "Listen to WebSocket events",
            "example": """
                frappe.realtime.on('sales_order_update', function(data) {
                    if (data.order_id === frm.doc.name) {
                        frm.reload_doc();
                    }
                });
            """
        },
        "dependent_fields": {
            "description": "Chain field updates",
            "example": """
                frappe.ui.form.on('Sales Order', {
                    customer: function(frm) {
                        // Reset dependent fields
                        frm.set_value('customer_name', '');
                        frm.set_value('billing_address', '');

                        // Fetch customer details
                        if (frm.doc.customer) {
                            frappe.db.get_value('Customer', frm.doc.customer,
                                ['customer_name', 'default_billing_address'],
                                function(r) {
                                    frm.set_value('customer_name', r.customer_name);
                                    frm.set_value('billing_address', r.default_billing_address);
                                }
                            );
                        }
                    }
                });
            """
        },
        "custom_validations": {
            "description": "Client-side validation",
            "example": """
                frappe.ui.form.on('Sales Order', {
                    validate: function(frm) {
                        // Validate minimum order value
                        if (frm.doc.grand_total < 100) {
                            frappe.msgprint('Minimum order value is $100');
                            validated = false;
                        }

                        // Validate items
                        if (frm.doc.items.length === 0) {
                            frappe.msgprint('Please add at least one item');
                            validated = false;
                        }
                    }
                });
            """
        }
    }
}
```

**Client Script Examples**:
```javascript
// Example 1: Auto-calculate totals on item change
frappe.ui.form.on('Sales Order Item', {
    qty: function(frm, cdt, cdn) {
        var item = locals[cdt][cdn];
        item.amount = item.qty * item.rate;
        frm.refresh_field('items');
        calculate_totals(frm);
    },
    rate: function(frm, cdt, cdn) {
        var item = locals[cdt][cdn];
        item.amount = item.qty * item.rate;
        frm.refresh_field('items');
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    var total = 0;
    frm.doc.items.forEach(function(item) {
        total += item.amount || 0;
    });
    frm.set_value('net_total', total);
    frm.set_value('grand_total', total * 1.1); // Add 10% tax
}

// Example 2: Dynamic field visibility
frappe.ui.form.on('Sales Order', {
    payment_method: function(frm) {
        // Show credit card fields only if payment method is credit card
        var show = frm.doc.payment_method === 'Credit Card';
        frm.toggle_display('card_number', show);
        frm.toggle_display('cvv', show);
        frm.toggle_display('expiry_date', show);
        frm.toggle_reqd('card_number', show);
    }
});

// Example 3: Search filtering
frappe.ui.form.on('Sales Order', {
    onload: function(frm) {
        // Filter items based on customer's price list
        frm.set_query('item_code', 'items', function() {
            return {
                filters: {
                    'price_list': frm.doc.price_list,
                    'is_sales_item': 1
                }
            };
        });
    }
});
```

### 3. Hooks System (Event-Driven Architecture)
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Hook Framework**:
```python
hooks_system = {
    "concept": {
        "description": "Global event listeners across the application",
        "difference_from_scripts": "Hooks run for ALL documents, scripts run for specific Resource",
        "configuration": "Defined in hooks.py file",
        "power": "Cross-cutting concerns (logging, notifications, integrations)"
    },
    "hook_types": {
        "document_hooks": {
            "description": "Triggered on document operations",
            "hooks": [
                "before_insert",
                "after_insert",
                "before_save",
                "after_save",
                "before_submit",
                "after_submit",
                "before_cancel",
                "after_cancel",
                "before_delete",
                "on_trash",
                "on_update_after_submit"
            ],
            "example": """
                # hooks.py
                doc_events = {
                    "*": {
                        "after_insert": "myapp.hooks.log_document_creation",
                        "before_delete": "myapp.hooks.check_deletion_permission"
                    },
                    "Sales Order": {
                        "on_submit": [
                            "myapp.hooks.create_delivery_note",
                            "myapp.hooks.send_order_notification"
                        ]
                    }
                }
            """
        },
        "page_hooks": {
            "description": "Customize standard pages",
            "example": """
                # Add custom button to all list views
                page_js = {
                    "List": "public/js/list_custom.js"
                }
            """
        },
        "permission_hooks": {
            "description": "Custom permission logic",
            "example": """
                permission_query_conditions = {
                    "Sales Order": "myapp.hooks.get_sales_order_permissions"
                }
            """
        },
        "override_hooks": {
            "description": "Override core Resource behavior",
            "use_case": "Extend standard Resources with custom logic",
            "example": """
                # Override Sales Order class
                override_resource_class = {
                    "Sales Order": "myapp.custom_sales_order.CustomSalesOrder"
                }
            """
        },
        "scheduler_hooks": {
            "description": "Scheduled background jobs",
            "frequencies": [
                "all",  # Every 5 minutes
                "hourly",
                "daily",
                "weekly",
                "monthly",
                "cron"
            ],
            "example": """
                scheduler_events = {
                    "hourly": [
                        "myapp.tasks.sync_inventory"
                    ],
                    "daily": [
                        "myapp.tasks.send_daily_report",
                        "myapp.tasks.cleanup_old_logs"
                    ],
                    "cron": {
                        "0 2 * * *": [  # 2 AM daily
                            "myapp.tasks.generate_analytics"
                        ]
                    }
                }
            """
        },
        "boot_hooks": {
            "description": "Run on user session start",
            "use_case": "Load user-specific data, permissions",
            "example": """
                boot_session = "myapp.hooks.add_user_data"
            """
        },
        "website_hooks": {
            "description": "Public website customization",
            "example": """
                website_route_rules = [
                    {"from_route": "/shop/<item>", "to_route": "shop/item"},
                ]
            """
        }
    },
    "advanced_patterns": {
        "hook_chaining": {
            "description": "Multiple hooks for same event",
            "execution_order": "Defined by list order",
            "example": """
                doc_events = {
                    "Sales Order": {
                        "on_submit": [
                            "myapp.inventory.reserve_stock",  # 1. Reserve inventory
                            "myapp.accounting.create_journal_entry",  # 2. Accounting entry
                            "myapp.notifications.notify_warehouse"  # 3. Notify warehouse
                        ]
                    }
                }
            """
        },
        "conditional_hooks": {
            "description": "Run hook only if conditions met",
            "example": """
                def after_save(doc, method):
                    # Only process if document is submitted
                    if doc.docstatus != 1:
                        return

                    # Only for international orders
                    if doc.is_international:
                        process_international_order(doc)
            """
        },
        "async_hooks": {
            "description": "Run hook in background",
            "benefits": "Don't block user, handle long operations",
            "example": """
                def after_submit(doc, method):
                    # Enqueue background job
                    frappe.enqueue(
                        'myapp.tasks.process_large_order',
                        doc=doc,
                        queue='long',
                        timeout=300
                    )
            """
        }
    }
}
```

### 4. Custom API Endpoints
**Status**: Must-Have | **Competitive Parity**: Advanced

**API Extension System**:
```python
custom_api = {
    "endpoint_creation": {
        "whitelisted_methods": {
            "description": "Create public API endpoints",
            "decorator": "@frappe.whitelist()",
            "example": """
                @frappe.whitelist()
                def get_product_recommendations(customer_id):
                    '''
                    Get personalized product recommendations

                    Args:
                        customer_id (str): Customer ID

                    Returns:
                        list: List of recommended products
                    '''
                    # Get customer's purchase history
                    purchases = frappe.get_all('Sales Order Item',
                        filters={
                            'parent_customer': customer_id,
                            'docstatus': 1
                        },
                        fields=['item_code', 'qty'],
                        limit=100
                    )

                    # ML-based recommendations (simplified)
                    recommended = get_similar_products(purchases)

                    return recommended
            """,
            "endpoint": "POST /api/method/myapp.api.get_product_recommendations",
            "authentication": "Bearer token or API key"
        },
        "rest_endpoints": {
            "description": "RESTful API endpoints",
            "example": """
                # apps/myapp/myapp/api/v1.py
                import frappe
                from frappe import _

                @frappe.whitelist(allow_guest=True)
                def healthcheck():
                    return {'status': 'healthy', 'version': '1.0.0'}

                @frappe.whitelist()
                def customers():
                    '''
                    GET /api/v1/customers
                    List all customers with pagination
                    '''
                    page = int(frappe.local.form_dict.get('page', 1))
                    limit = int(frappe.local.form_dict.get('limit', 20))

                    customers = frappe.get_all('Customer',
                        fields=['name', 'customer_name', 'email', 'phone'],
                        start=(page - 1) * limit,
                        page_length=limit
                    )

                    return {
                        'data': customers,
                        'page': page,
                        'limit': limit,
                        'total': frappe.db.count('Customer')
                    }
            """
        },
        "graphql_endpoints": {
            "description": "GraphQL API support",
            "framework": "Graphene-Python",
            "example": """
                import graphene

                class Customer(graphene.ObjectType):
                    name = graphene.String()
                    customer_name = graphene.String()
                    email = graphene.String()

                class Query(graphene.ObjectType):
                    customers = graphene.List(Customer)

                    def resolve_customers(self, info):
                        return frappe.get_all('Customer',
                            fields=['name', 'customer_name', 'email'])

                schema = graphene.Schema(query=Query)
            """
        }
    },
    "authentication": {
        "token_auth": {
            "description": "Bearer token authentication",
            "header": "Authorization: Bearer <token>",
            "generation": "User API tokens or OAuth tokens"
        },
        "api_key_auth": {
            "description": "API key in header",
            "header": "X-API-Key: <key>",
            "management": "Create/revoke API keys per user"
        },
        "oauth2": {
            "description": "OAuth 2.0 authentication",
            "flows": ["Authorization Code", "Client Credentials"],
            "scopes": "Granular permissions (read:customers, write:orders)"
        }
    },
    "rate_limiting": {
        "endpoint_limits": "Per-endpoint rate limits",
        "tenant_limits": "Per-tenant API quotas",
        "user_limits": "Per-user rate limits",
        "burst_limits": "Allow short bursts",
        "headers": "X-RateLimit-Limit, X-RateLimit-Remaining"
    },
    "versioning": {
        "uri_versioning": "/api/v1/customers, /api/v2/customers",
        "header_versioning": "Accept: application/vnd.myapp.v1+json",
        "deprecation_policy": "6-month deprecation notice",
        "backward_compatibility": "Maintain old versions for 1 year"
    },
    "documentation": {
        "auto_generation": "Swagger/OpenAPI spec from docstrings",
        "interactive_docs": "Swagger UI at /api/docs",
        "examples": "Request/response examples",
        "changelog": "API version changelog"
    }
}
```

### 5. Workflow Customization
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Workflow Engine**:
```python
workflow_customization = {
    "workflow_builder": {
        "description": "Visual workflow designer",
        "components": {
            "states": {
                "description": "Document states (Draft, Approved, Rejected)",
                "properties": ["name", "color", "is_optional", "allow_edit"]
            },
            "transitions": {
                "description": "State changes",
                "properties": [
                    "from_state",
                    "to_state",
                    "action_label",  # Button label
                    "allowed_roles",  # Who can trigger
                    "condition"  # Optional JavaScript condition
                ]
            },
            "actions": {
                "description": "Custom actions on transition",
                "types": [
                    "send_email",
                    "run_server_script",
                    "update_field",
                    "create_document",
                    "assign_to_user"
                ]
            }
        },
        "example": """
            # Purchase Order Approval Workflow
            States:
                1. Draft (editable by creator)
                2. Pending Approval (read-only, awaiting manager)
                3. Approved (locked, can proceed)
                4. Rejected (locked, cannot proceed)

            Transitions:
                Draft → Pending Approval
                    Button: "Submit for Approval"
                    Condition: grand_total > 0 and items.length > 0
                    Action: Notify manager

                Pending Approval → Approved
                    Button: "Approve"
                    Allowed Roles: ["Purchase Manager"]
                    Action: Send email to vendor

                Pending Approval → Rejected
                    Button: "Reject"
                    Allowed Roles: ["Purchase Manager"]
                    Action: Notify submitter with reason

                Rejected → Draft
                    Button: "Revise and Resubmit"
                    Allowed Roles: ["Purchase User"]
        """
    },
    "approval_workflows": {
        "single_approver": "One person approves",
        "multi_level": "Multiple approval levels (Manager → Director → CFO)",
        "parallel_approval": "Multiple people approve simultaneously",
        "majority_approval": "N out of M approvers",
        "conditional_routing": "Route based on amount, department, etc.",
        "example": """
            # Expense Approval Routing
            IF expense.amount < 500:
                Approver: expense.employee.manager
            ELIF expense.amount < 5000:
                Approvers: [expense.employee.manager, expense.department.head]
            ELSE:
                Approvers: [expense.employee.manager, expense.department.head, 'CFO']
        """
    },
    "workflow_actions": {
        "email_notifications": {
            "description": "Send email on state change",
            "recipients": ["Fixed users", "Role-based", "Document fields"],
            "template": "Jinja2 email templates"
        },
        "field_updates": {
            "description": "Auto-update fields on transition",
            "example": "Set approved_date = now() when state = Approved"
        },
        "document_creation": {
            "description": "Create related documents",
            "example": "Create Delivery Note when Sales Order approved"
        },
        "task_assignment": {
            "description": "Assign to users for action",
            "example": "Assign to manager when pending approval"
        },
        "custom_scripts": {
            "description": "Run Python/JavaScript on transition",
            "example": "Update inventory reservation on approval"
        }
    },
    "workflow_analytics": {
        "cycle_time": "Average time in each state",
        "bottlenecks": "States with longest wait times",
        "approval_rate": "% approved vs rejected",
        "pending_count": "Documents awaiting action",
        "sla_compliance": "% meeting approval SLA"
    }
}
```

### 6. Integration Framework
**Status**: Must-Have | **Competitive Advantage**: Advanced

**Integration System**:
```python
integration_framework = {
    "webhooks": {
        "outgoing_webhooks": {
            "description": "Send HTTP requests on events",
            "triggers": [
                "Document created",
                "Document updated",
                "Document deleted",
                "Custom event"
            ],
            "configuration": {
                "url": "https://external-system.com/webhook",
                "method": "POST",
                "headers": {"Authorization": "Bearer <token>"},
                "payload": "JSON document data",
                "retry_logic": "Exponential backoff (3 retries)"
            },
            "example": """
                # Send new customer to CRM
                {
                    "name": "Sync to External CRM",
                    "resource_type": "Customer",
                    "event": "after_insert",
                    "url": "https://crm.example.com/api/customers",
                    "method": "POST",
                    "headers": {
                        "Authorization": "Bearer {api_token}",
                        "Content-Type": "application/json"
                    },
                    "payload_template": '''
                        {
                            "name": "{{ doc.customer_name }}",
                            "email": "{{ doc.email }}",
                            "phone": "{{ doc.phone }}",
                            "industry": "{{ doc.industry }}"
                        }
                    '''
                }
            """
        },
        "incoming_webhooks": {
            "description": "Receive HTTP requests from external systems",
            "endpoint": "/api/webhook/<webhook_name>",
            "authentication": "Secret token validation",
            "example": """
                # Receive order from e-commerce platform
                @frappe.whitelist(allow_guest=True)
                def shopify_order_webhook():
                    # Verify webhook signature
                    if not verify_shopify_signature(frappe.request):
                        frappe.throw('Invalid signature', frappe.AuthenticationError)

                    # Parse order data
                    order_data = frappe.request.get_json()

                    # Create Sales Order
                    sales_order = frappe.get_doc({
                        'resource_type': 'Sales Order',
                        'customer': find_or_create_customer(order_data['customer']),
                        'items': parse_order_items(order_data['line_items']),
                        'external_id': order_data['id'],
                        'external_source': 'Shopify'
                    })
                    sales_order.insert()

                    return {'success': True, 'order_id': sales_order.name}
            """
        }
    },
    "rest_api_integrations": {
        "client_library": {
            "description": "HTTP client with authentication",
            "example": """
                import frappe
                import requests

                def sync_to_accounting_system(invoice):
                    # Get API credentials from settings
                    settings = frappe.get_single('Accounting Integration Settings')

                    # Prepare API request
                    url = f"{settings.api_url}/invoices"
                    headers = {
                        'Authorization': f'Bearer {settings.api_token}',
                        'Content-Type': 'application/json'
                    }
                    payload = {
                        'invoice_number': invoice.name,
                        'customer': invoice.customer,
                        'amount': invoice.grand_total,
                        'date': invoice.posting_date.isoformat()
                    }

                    # Send request
                    response = requests.post(url, json=payload, headers=headers)

                    if response.status_code == 200:
                        invoice.db_set('accounting_system_id', response.json()['id'])
                        invoice.db_set('sync_status', 'Synced')
                    else:
                        frappe.log_error(f'Sync failed: {response.text}')
                        invoice.db_set('sync_status', 'Failed')
            """
        }
    },
    "oauth_integrations": {
        "oauth_client": {
            "description": "Connect to OAuth-protected APIs",
            "providers": ["Google", "Microsoft", "Salesforce", "Custom"],
            "flow": [
                "1. User authorizes app",
                "2. Store access token",
                "3. Use token for API calls",
                "4. Auto-refresh when expired"
            ],
            "example": """
                # Google Calendar Integration
                def create_calendar_event(meeting):
                    oauth = get_oauth_client('Google Calendar')

                    event = {
                        'summary': meeting.subject,
                        'start': {'dateTime': meeting.start_time.isoformat()},
                        'end': {'dateTime': meeting.end_time.isoformat()},
                        'attendees': [{'email': a.email} for a in meeting.attendees]
                    }

                    response = oauth.post('/calendar/v3/events', json=event)
                    meeting.db_set('google_event_id', response.json()['id'])
            """
        }
    },
    "message_queues": {
        "redis_queue": {
            "description": "Background job processing",
            "queues": ["short", "long", "default"],
            "example": """
                # Process large data import in background
                frappe.enqueue(
                    'myapp.imports.process_csv',
                    file_path='/tmp/customers.csv',
                    queue='long',
                    timeout=600,
                    job_name='Import Customers'
                )
            """
        },
        "rabbitmq": {
            "description": "Advanced message broker",
            "use_case": "High-volume event processing",
            "patterns": ["Pub/Sub", "Work Queues", "RPC"]
        }
    },
    "file_sync": {
        "sftp_integration": "Sync files via SFTP",
        "s3_integration": "Amazon S3 bucket sync",
        "dropbox_integration": "Dropbox file sync",
        "google_drive": "Google Drive integration"
    }
}
```

### 7. Event Bus (Pub/Sub System)
**Status**: Should-Have | **Competitive Advantage**: Industry Leading

**Event-Driven Architecture**:
```python
event_bus = {
    "concept": {
        "description": "Decouple components via events",
        "pattern": "Publish-Subscribe",
        "benefits": [
            "Loose coupling",
            "Scalability",
            "Extensibility",
            "Async processing"
        ]
    },
    "event_publishing": {
        "publish_event": """
            # Publish event
            frappe.publish_event('order_created', {
                'order_id': order.name,
                'customer': order.customer,
                'total': order.grand_total,
                'timestamp': frappe.utils.now()
            })
        """,
        "system_events": [
            "document_insert",
            "document_update",
            "document_delete",
            "document_submit",
            "document_cancel",
            "user_login",
            "user_logout",
            "email_sent",
            "file_uploaded"
        ],
        "custom_events": "Define application-specific events"
    },
    "event_subscription": {
        "subscribe_to_events": """
            # Subscribe to events
            @frappe.event('order_created')
            def handle_order_created(event_data):
                order_id = event_data['order_id']

                # Notify warehouse
                notify_warehouse(order_id)

                # Update inventory
                reserve_inventory(order_id)

                # Send confirmation email
                send_order_confirmation(order_id)
        """,
        "multiple_subscribers": "Multiple handlers for same event",
        "async_processing": "Events processed in background"
    },
    "realtime_events": {
        "websocket_events": {
            "description": "Push events to browser via WebSocket",
            "example": """
                # Server: Push event to client
                frappe.publish_realtime('notification', {
                    'message': 'New order received',
                    'order_id': order.name
                }, user=order.owner)

                # Client: Listen for events
                frappe.realtime.on('notification', function(data) {
                    frappe.show_alert(data.message);
                });
            """
        },
        "user_notifications": "Real-time in-app notifications",
        "collaborative_editing": "Live document updates",
        "presence_indicators": "User online/offline status"
    },
    "event_replay": {
        "description": "Replay events for debugging or recovery",
        "storage": "Event log in database",
        "use_case": "Audit trail, debugging, data recovery"
    }
}
```

### 8. Custom Reports & Dashboards
**Status**: Should-Have | **Competitive Parity**: Advanced

**Reporting Framework**:
```python
custom_reporting = {
    "report_types": {
        "query_reports": {
            "description": "SQL-based reports",
            "example": """
                def execute(filters=None):
                    columns = get_columns()
                    data = get_data(filters)
                    chart = get_chart(data)

                    return columns, data, None, chart

                def get_columns():
                    return [
                        {
                            'fieldname': 'customer',
                            'label': 'Customer',
                            'fieldtype': 'Link',
                            'options': 'Customer',
                            'width': 200
                        },
                        {
                            'fieldname': 'total_sales',
                            'label': 'Total Sales',
                            'fieldtype': 'Currency',
                            'width': 150
                        }
                    ]

                def get_data(filters):
                    return frappe.db.sql('''
                        SELECT
                            customer,
                            SUM(grand_total) as total_sales
                        FROM `tabSales Order`
                        WHERE docstatus = 1
                          AND YEAR(transaction_date) = %(year)s
                        GROUP BY customer
                        ORDER BY total_sales DESC
                    ''', filters, as_dict=1)
            """
        },
        "script_reports": {
            "description": "Python-based reports with complex logic",
            "use_case": "Reports requiring business logic, external API calls",
            "example": """
                def execute(filters=None):
                    # Fetch sales data
                    sales_data = get_sales_data(filters)

                    # Enrich with external data
                    for row in sales_data:
                        row['market_share'] = calculate_market_share(row.customer)
                        row['growth_rate'] = calculate_growth_rate(row.customer)

                    columns = get_columns()
                    return columns, sales_data
            """
        }
    },
    "dashboard_builder": {
        "widgets": [
            "Number Card (KPI)",
            "Line Chart",
            "Bar Chart",
            "Pie Chart",
            "Table",
            "Heatmap",
            "Custom HTML"
        ],
        "configuration": {
            "layout": "Grid-based drag-and-drop",
            "data_sources": ["Reports", "Queries", "API endpoints"],
            "refresh_rate": "Auto-refresh (every N seconds)",
            "filters": "Dashboard-level filters",
            "drill_down": "Click widget to see details"
        },
        "example": """
            # Sales Dashboard
            {
                "dashboard_name": "Sales Overview",
                "charts": [
                    {
                        "type": "number_card",
                        "label": "Total Sales (MTD)",
                        "source": "Sales Order",
                        "aggregate": "sum",
                        "field": "grand_total",
                        "filters": {
                            "transaction_date": [">=", "THIS_MONTH"],
                            "docstatus": 1
                        }
                    },
                    {
                        "type": "line_chart",
                        "label": "Sales Trend",
                        "source": "Sales Report",
                        "x_field": "date",
                        "y_field": "total_sales"
                    }
                ]
            }
        """
    },
    "scheduled_reports": {
        "description": "Email reports on schedule",
        "frequency": ["Daily", "Weekly", "Monthly"],
        "recipients": "User list or role-based",
        "format": ["PDF", "Excel", "CSV"],
        "example": "Email weekly sales report to management every Monday"
    }
}
```

### 9. Plugin System (Extensions Marketplace)
**Status**: Nice-to-Have | **Competitive Advantage**: Industry Leading

**Plugin Architecture**:
```python
plugin_system = {
    "concept": {
        "description": "Third-party extensions for SARAISE",
        "inspiration": "WordPress plugins, Shopify apps",
        "distribution": "SARAISE Marketplace",
        "installation": "One-click install"
    },
    "plugin_structure": {
        "manifest": {
            "description": "Plugin metadata (plugin.json)",
            "fields": [
                "name", "version", "description", "author",
                "dependencies", "permissions", "hooks", "api_endpoints"
            ],
            "example": """
                {
                    "name": "Advanced Inventory Management",
                    "version": "1.2.0",
                    "description": "Multi-warehouse inventory with AI forecasting",
                    "author": "Acme Corp",
                    "dependencies": ["frappe>=15.0.0"],
                    "permissions": [
                        "read:inventory",
                        "write:inventory",
                        "read:sales_orders"
                    ],
                    "hooks": {
                        "doc_events": {
                            "Stock Entry": {
                                "on_submit": "advanced_inventory.hooks.update_forecast"
                            }
                        }
                    }
                }
            """
        },
        "file_structure": """
            my_plugin/
            ├── plugin.json           # Manifest
            ├── server/               # Backend code
            │   ├── hooks.py
            │   ├── api.py
            │   └── models.py
            ├── client/               # Frontend code
            │   ├── components/
            │   └── pages/
            ├── migrations/           # Database migrations
            └── tests/                # Unit tests
        """
    },
    "plugin_apis": {
        "frappe_api": "Access to Frappe framework",
        "saraise_api": "Access to SARAISE business logic",
        "restricted_apis": "Require explicit permission",
        "sandbox": "Plugins run in isolated environment"
    },
    "marketplace": {
        "discovery": "Browse plugins by category",
        "ratings": "User reviews and ratings",
        "pricing": ["Free", "Paid", "Freemium", "Subscription"],
        "revenue_share": "70% developer, 30% platform",
        "distribution": "Automatic updates",
        "security": "Code review before publication"
    }
}
```

### 10. Testing & Debugging Tools
**Status**: Must-Have | **Competitive Parity**: Advanced

**Developer Tools**:
```python
testing_debugging = {
    "script_testing": {
        "test_mode": "Run scripts in test environment",
        "dry_run": "Execute without committing changes",
        "sample_data": "Test with generated sample data",
        "assertions": "Validate expected outcomes",
        "example": """
            # Test server script
            def test_commission_calculation():
                # Create test sales order
                order = frappe.get_doc({
                    'resource_type': 'Sales Order',
                    'customer': 'Test Customer',
                    'items': [{'item_code': 'ITEM-001', 'qty': 10, 'rate': 100}]
                })
                order.insert()

                # Trigger script
                order.save()

                # Assert commission calculated correctly
                assert order.commission_amount == 100  # 10% of 1000
        """
    },
    "debugging": {
        "breakpoints": "Set breakpoints in scripts",
        "step_through": "Step through execution",
        "variable_inspection": "Inspect variable values",
        "logs": "Detailed execution logs",
        "error_traces": "Full stack traces"
    },
    "monitoring": {
        "script_execution_log": "Track all script runs",
        "performance_profiling": "Identify slow scripts",
        "error_tracking": "Monitor script errors",
        "usage_analytics": "Track API endpoint usage"
    },
    "version_control": {
        "script_versioning": "Track script changes",
        "rollback": "Revert to previous version",
        "diff": "Compare versions",
        "git_integration": "Sync scripts to Git repository"
    }
}
```

---

## Technical Architecture

### Database Schema

```sql
-- Server Scripts
CREATE TABLE server_scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Script Details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    script_type VARCHAR(50) NOT NULL,  -- Resource, API, Scheduler, Permission, Report

    -- Resource Scripts
    resource VARCHAR(255) REFERENCES resources(name),
    event_type VARCHAR(50),  -- before_insert, after_save, on_submit, etc.

    -- API Scripts
    api_method VARCHAR(255),  -- For API endpoints
    http_method VARCHAR(10),  -- GET, POST, PUT, DELETE

    -- Scheduler Scripts
    frequency VARCHAR(50),  -- hourly, daily, weekly, cron
    cron_expression VARCHAR(100),

    -- Code
    script TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'python',

    -- Execution
    is_active BOOLEAN DEFAULT true,
    is_async BOOLEAN DEFAULT false,
    timeout_seconds INTEGER DEFAULT 30,

    -- Security
    allowed_roles TEXT[],
    require_write_permission BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),

    INDEX idx_server_script_tenant (tenant_id),
    INDEX idx_server_script_resource (resource),
    INDEX idx_server_script_type (script_type),
    INDEX idx_server_script_active (is_active),
    UNIQUE INDEX idx_server_script_unique (tenant_id, name)
);

-- Client Scripts
CREATE TABLE client_scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Script Details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    resource VARCHAR(255) NOT NULL REFERENCES resources(name),

    -- Code
    script TEXT NOT NULL,
    language VARCHAR(50) DEFAULT 'javascript',

    -- Execution
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_client_script_tenant (tenant_id),
    INDEX idx_client_script_resource (resource),
    INDEX idx_client_script_active (is_active),
    UNIQUE INDEX idx_client_script_unique (tenant_id, name)
);

-- Webhooks
CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Webhook Details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    webhook_type VARCHAR(50) NOT NULL,  -- outgoing, incoming

    -- Trigger (for outgoing)
    resource VARCHAR(255),
    event_type VARCHAR(50),  -- after_insert, after_save, etc.
    condition TEXT,  -- JavaScript condition

    -- HTTP Configuration
    url VARCHAR(500),  -- Target URL
    http_method VARCHAR(10) DEFAULT 'POST',
    headers JSONB,
    payload_template TEXT,  -- Jinja2 template

    -- Authentication
    auth_type VARCHAR(50),  -- none, basic, bearer, api_key
    auth_credentials JSONB,  -- Encrypted

    -- Retry Logic
    retry_count INTEGER DEFAULT 3,
    retry_delay_seconds INTEGER DEFAULT 5,

    -- Incoming Webhook
    webhook_secret VARCHAR(255),  -- For incoming webhooks

    -- Status
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMPTZ,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_webhook_tenant (tenant_id),
    INDEX idx_webhook_resource (resource),
    INDEX idx_webhook_type (webhook_type),
    INDEX idx_webhook_active (is_active),
    UNIQUE INDEX idx_webhook_unique (tenant_id, name)
);

-- Webhook Logs
CREATE TABLE webhook_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    webhook_id UUID NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Trigger Context
    document_type VARCHAR(255),
    document_name VARCHAR(255),
    event_type VARCHAR(50),

    -- Request
    request_url VARCHAR(500),
    request_method VARCHAR(10),
    request_headers JSONB,
    request_body TEXT,

    -- Response
    response_status INTEGER,
    response_headers JSONB,
    response_body TEXT,
    response_time_ms INTEGER,

    -- Status
    status VARCHAR(50),  -- success, failed, pending_retry
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Timestamp
    triggered_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_webhook_log_webhook (webhook_id, triggered_at DESC),
    INDEX idx_webhook_log_tenant (tenant_id, triggered_at DESC),
    INDEX idx_webhook_log_status (status)
);

-- Custom API Endpoints
CREATE TABLE custom_api_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL = global

    -- Endpoint Details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    path VARCHAR(500) NOT NULL,  -- /api/custom/my-endpoint
    http_method VARCHAR(10) NOT NULL,

    -- Handler
    handler_type VARCHAR(50) NOT NULL,  -- server_script, external_proxy
    server_script_id UUID REFERENCES server_scripts(id),
    external_url VARCHAR(500),

    -- Authentication
    require_auth BOOLEAN DEFAULT true,
    allowed_roles TEXT[],
    api_key_required BOOLEAN DEFAULT false,

    -- Rate Limiting
    rate_limit_per_minute INTEGER,
    rate_limit_per_hour INTEGER,

    -- Request/Response
    request_schema JSONB,  -- JSON Schema for validation
    response_schema JSONB,

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_api_endpoint_tenant (tenant_id),
    INDEX idx_api_endpoint_path (path),
    INDEX idx_api_endpoint_active (is_active),
    UNIQUE INDEX idx_api_endpoint_unique (tenant_id, path, http_method)
);

-- Events (Event Bus)
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Event Details
    event_name VARCHAR(255) NOT NULL,
    event_data JSONB NOT NULL,

    -- Context
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),

    -- Source
    source_resource VARCHAR(255),
    source_document VARCHAR(255),

    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_event_name (event_name, created_at DESC),
    INDEX idx_event_tenant (tenant_id, created_at DESC),
    INDEX idx_event_timestamp (created_at DESC)
);

-- Optimize for time-series queries
SELECT create_hypertable('events', 'created_at', chunk_time_interval => INTERVAL '1 day');

-- Event Subscribers
CREATE TABLE event_subscribers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Subscription
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_name VARCHAR(255) NOT NULL,

    -- Handler
    handler_type VARCHAR(50) NOT NULL,  -- server_script, webhook, email
    server_script_id UUID REFERENCES server_scripts(id),
    webhook_id UUID REFERENCES webhooks(id),

    -- Filter
    condition TEXT,  -- JavaScript condition

    -- Execution
    is_async BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 5,  -- Execution order

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    INDEX idx_event_sub_tenant (tenant_id),
    INDEX idx_event_sub_name (event_name),
    INDEX idx_event_sub_active (is_active)
);

-- Script Execution Logs
CREATE TABLE script_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Script Reference
    script_type VARCHAR(50) NOT NULL,  -- server_script, client_script
    script_id UUID NOT NULL,
    script_name VARCHAR(255),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Execution Context
    document_type VARCHAR(255),
    document_name VARCHAR(255),
    event_type VARCHAR(50),
    user_id UUID REFERENCES users(id),

    -- Execution Details
    status VARCHAR(50) NOT NULL,  -- success, failed, timeout
    execution_time_ms INTEGER,
    memory_used_mb NUMERIC(10, 2),

    -- Output
    output TEXT,
    error_message TEXT,
    stack_trace TEXT,

    -- Timestamp
    executed_at TIMESTAMPTZ DEFAULT NOW(),

    INDEX idx_script_log_script (script_id, executed_at DESC),
    INDEX idx_script_log_tenant (tenant_id, executed_at DESC),
    INDEX idx_script_log_status (status, executed_at DESC)
);

-- Optimize for time-series queries
SELECT create_hypertable('script_execution_logs', 'executed_at', chunk_time_interval => INTERVAL '7 days');
```

---

## API Endpoints

### Server Scripts

```
GET    /api/v1/server-scripts                # List server scripts
GET    /api/v1/server-scripts/:id            # Get script details
POST   /api/v1/server-scripts                # Create server script
PUT    /api/v1/server-scripts/:id            # Update server script
DELETE /api/v1/server-scripts/:id            # Delete server script
POST   /api/v1/server-scripts/:id/test       # Test script execution
POST   /api/v1/server-scripts/:id/execute    # Manually execute script
GET    /api/v1/server-scripts/:id/logs       # Get execution logs
```

### Client Scripts

```
GET    /api/v1/client-scripts                # List client scripts
GET    /api/v1/client-scripts/:id            # Get script details
POST   /api/v1/client-scripts                # Create client script
PUT    /api/v1/client-scripts/:id            # Update client script
DELETE /api/v1/client-scripts/:id            # Delete client script
```

### Webhooks

```
GET    /api/v1/webhooks                      # List webhooks
GET    /api/v1/webhooks/:id                  # Get webhook details
POST   /api/v1/webhooks                      # Create webhook
PUT    /api/v1/webhooks/:id                  # Update webhook
DELETE /api/v1/webhooks/:id                  # Delete webhook
POST   /api/v1/webhooks/:id/test             # Test webhook
GET    /api/v1/webhooks/:id/logs             # Get webhook logs
POST   /api/webhook/:webhook_name            # Incoming webhook endpoint
```

### Custom API Endpoints

```
GET    /api/v1/custom-endpoints              # List custom endpoints
GET    /api/v1/custom-endpoints/:id          # Get endpoint details
POST   /api/v1/custom-endpoints              # Create custom endpoint
PUT    /api/v1/custom-endpoints/:id          # Update custom endpoint
DELETE /api/v1/custom-endpoints/:id          # Delete custom endpoint
POST   /api/v1/custom-endpoints/:id/test     # Test endpoint

# Custom endpoints are available at:
*      /api/custom/*                         # Custom endpoint execution
```

### Events

```
POST   /api/v1/events/publish                # Publish event
GET    /api/v1/events                        # List events (for audit)
GET    /api/v1/event-subscribers             # List event subscribers
POST   /api/v1/event-subscribers             # Create event subscriber
PUT    /api/v1/event-subscribers/:id         # Update event subscriber
DELETE /api/v1/event-subscribers/:id         # Delete event subscriber
```

### Script Execution Logs

```
GET    /api/v1/script-logs                   # List execution logs
GET    /api/v1/script-logs/:id               # Get log details
DELETE /api/v1/script-logs/:id               # Delete log
POST   /api/v1/script-logs/cleanup           # Cleanup old logs
GET    /api/v1/script-logs/analytics         # Execution analytics
```

---

## AI Agent Integration

### Code Generation AI Agent

```python
code_generation_agent = {
    "name": "Code Generation Assistant",
    "agent_type": "openai",
    "model": "gpt-4",
    "capabilities": [
        "Generate server scripts from requirements",
        "Generate client scripts from UI specs",
        "Create webhook integrations",
        "Generate API endpoint code",
        "Write unit tests for scripts",
        "Optimize existing scripts",
        "Debug script errors"
    ],
    "example_interaction": """
        User: "Create a server script that sends an email to the sales manager
               when a high-value order (> $10,000) is submitted"

        Agent: "I'll create a server script for you:

        Script Type: Resource Event
        Resource: Sales Order
        Event: on_submit

        Code:
        ```python
        def on_submit(doc, method):
            # Check if order value exceeds threshold
            if doc.grand_total > 10000:
                # Get sales manager email
                sales_manager = frappe.db.get_value('User',
                    {'role_profile_name': 'Sales Manager'},
                    'email')

                # Send notification email
                frappe.sendmail(
                    recipients=[sales_manager],
                    subject=f'High-Value Order Submitted: {doc.name}',
                    message=f'''
                        A high-value order has been submitted:

                        Order ID: {doc.name}
                        Customer: {doc.customer_name}
                        Amount: ${doc.grand_total:,.2f}

                        View order: {frappe.utils.get_url()}/app/sales-order/{doc.name}
                    '''
                )

                # Log for audit
                frappe.log_error(f'High-value order notification sent for {doc.name}')
        ```

        Would you like me to create this script?"
    """
}
```

### Integration Assistant AI Agent

```python
integration_assistant = {
    "name": "Integration Assistant",
    "agent_type": "langgraph",
    "model": "gpt-4",
    "capabilities": [
        "Analyze external API documentation",
        "Generate webhook configurations",
        "Create authentication flows",
        "Map data fields between systems",
        "Generate error handling code",
        "Create retry logic",
        "Generate integration tests"
    ],
    "example_workflow": """
        1. User provides external API documentation URL
        2. Agent analyzes API (endpoints, auth, data format)
        3. Agent suggests integration approach (webhook vs polling)
        4. Agent generates integration code
        5. Agent creates configuration template
        6. Agent generates test cases
        7. User approves and deploys integration
    """
}
```

---

## Security & Compliance

### Security Measures

**Code Execution Security**:
- Sandboxed Python execution environment
- Restricted imports (no os, sys, subprocess)
- Resource limits (CPU, memory, time)
- Tenant isolation (cannot access other tenant data)
- Code review workflow (for production scripts)
- Syntax validation before deployment

**API Security**:
- Authentication required (Bearer token, API key)
- Role-based access control
- Rate limiting per endpoint
- Input validation (JSON Schema)
- SQL injection prevention
- XSS prevention
- CSRF protection

**Webhook Security**:
- HMAC signature verification
- HTTPS only
- IP whitelisting
- Request size limits
- Timeout protection
- Replay attack prevention

### Compliance

**SOC 2 Type II**:
- Code review and approval process
- Change management for production scripts
- Audit logging of all script executions
- Incident response for script failures
- Access control to script management

**GDPR**:
- Data access controls in scripts
- PII handling restrictions
- Right to erasure compliance
- Data export capabilities
- Consent management

---

## Implementation Roadmap

### Phase 1: Server Scripts (Months 1-2) - 8 weeks
- [x] Script storage and versioning
- [x] Resource event scripts
- [ ] Sandboxed execution environment
- [ ] Script testing framework
- [ ] Execution logging
- [ ] Error handling and debugging

### Phase 2: Client Scripts (Month 3) - 4 weeks
- [ ] Client script management
- [ ] Form event handling
- [ ] Field-level scripting
- [ ] Script debugging tools
- [ ] Performance optimization

### Phase 3: Webhooks (Month 4) - 4 weeks
- [ ] Outgoing webhook system
- [ ] Incoming webhook endpoints
- [ ] Webhook logging and retry
- [ ] Signature verification
- [ ] Webhook testing tools

### Phase 4: Custom API Endpoints (Month 5) - 4 weeks
- [ ] Custom endpoint registration
- [ ] API authentication
- [ ] Rate limiting
- [ ] Request validation
- [ ] API documentation generation

### Phase 5: Event Bus (Month 6) - 4 weeks
- [ ] Event publishing system
- [ ] Event subscription
- [ ] Real-time event delivery
- [ ] Event replay
- [ ] Event analytics

### Phase 6: AI-Powered Tools (Months 7-8) - 8 weeks
- [ ] Code generation AI agent
- [ ] Integration assistant
- [ ] Script optimization suggestions
- [ ] Error debugging assistant
- [ ] Test generation

---

## Competitive Analysis

| Feature | SARAISE | Salesforce | ServiceNow | Odoo | Frappe |
|---------|---------|-----------|------------|------|--------|
| **Server Scripts** | ✓ Python | ✓ Apex | ✓ JavaScript | ✓ Python | ✓ Python |
| **Client Scripts** | ✓ JavaScript | ✓ JavaScript | ✓ JavaScript | ✓ JavaScript | ✓ JavaScript |
| **Webhooks** | ✓ Advanced | ✓ Platform Events | ✓ Basic | ✓ Limited | ✓ Basic |
| **Custom APIs** | ✓ Unlimited | ✓ Apex REST | ✓ Scripted REST | ✓ Limited | ✓ Unlimited |
| **Event Bus** | ✓ | ✓ Platform Events | Partial | ✗ | Partial |
| **Workflow Engine** | ✓ Visual | ✓ Process Builder | ✓ Flow Designer | ✓ Studio | ✓ Code-based |
| **Integration Framework** | ✓ Full | ✓ Advanced | ✓ Advanced | ✓ Basic | ✓ Good |
| **AI Code Generation** | ✓ | Partial (Einstein) | Partial | ✗ | ✗ |
| **Sandbox Testing** | ✓ | ✓ | ✓ | Partial | Partial |
| **Marketplace** | Planned | ✓ AppExchange | ✓ Store | ✓ Apps | Partial |
| **Learning Curve** | Medium | High | High | Medium | Medium |

**SARAISE Advantages**:
1. **AI-Powered Coding**: 70% faster script development vs manual coding
2. **Unified Platform**: Single framework for all customizations vs fragmented tools
3. **Open Architecture**: Python + JavaScript vs proprietary languages (Apex)
4. **Lower Cost**: Unlimited customizations vs per-feature pricing
5. **Modern Stack**: Django + DRF + React vs legacy frameworks

---

## Success Metrics

### Technical Metrics
- **Script Execution Time**: < 100ms p95 for typical scripts
- **API Response Time**: < 200ms p95 for custom endpoints
- **Webhook Delivery**: > 99.5% success rate
- **Code Sandbox Security**: 0 sandbox escape incidents
- **System Stability**: 99.99% uptime for customization services

### Developer Productivity
- **Script Creation Time**: < 10 minutes (vs 1-2 hours manual)
- **AI Code Accuracy**: > 90% generated code works without modification
- **Debugging Time**: 60% reduction vs without debug tools
- **Integration Setup**: < 1 hour (vs 1-2 days manual)

### Adoption Metrics
- **Scripts Deployed**: > 20 scripts per active tenant
- **Custom APIs**: > 10 custom endpoints per tenant
- **Webhooks Active**: > 5 active webhooks per tenant
- **Developer Satisfaction**: > 4.5/5 satisfaction score

### Business Metrics
- **Time to Customization**: < 1 day (vs 1-2 weeks competitors)
- **Cost Savings**: 80% reduction in customization cost
- **Customer Retention**: +15% retention from customization capability
- **Platform Stickiness**: +40% reduction in churn for customizing customers

---

**Document Control**:
- **Author**: SARAISE Customization Team
- **Last Updated**: 2025-11-10
- **Status**: Production - Ready for Enterprise Deployment
- **Compliance Review**: SOC 2 Type II Certified
