# Phase 12: Core Modules Part 3 — HR, Projects & Analytics

**Duration:** 5 weeks (Weeks 26-30)  
**Modules:** Human Resources, Project Management, Business Intelligence  
**Status:** ⏸️ BLOCKED (Awaiting Phase 11)  
**Prerequisites:** Phase 11 complete (Sales, Purchase, Inventory operational)

---

## Phase Objectives

Complete Core module layer with HR, project management, and analytics capabilities.

### Success Criteria
- [ ] 3 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] Payroll-to-GL integration verified
- [ ] BI dashboards operational
- [ ] Core modules complete (8 modules total)

---

## Week 26-27: Human Resources Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `human_resources` |
| Type | Core |
| Priority | P0 (Customer-Promised) |
| Dependencies | Tenant Management, Accounting |
| Spec Location | `docs/modules/02-core/human-resources/` |
| Timeline | 7-10 days |

### Key Entities

```python
# HR Core entities
- Employee (employee_id, user_id, department_id, position, status, tenant_id)
- Department (name, parent_id, manager_id, cost_center, tenant_id)
- Position (title, department_id, salary_grade, tenant_id)
- EmployeeContract (employee_id, start_date, end_date, type, salary, tenant_id)

# Time & Attendance
- Attendance (employee_id, date, check_in, check_out, status, tenant_id)
- Leave (employee_id, leave_type, start_date, end_date, status, tenant_id)
- LeaveType (name, days_per_year, carry_over, tenant_id)
- LeaveBalance (employee_id, leave_type_id, year, balance, used, tenant_id)

# Payroll
- PayrollPeriod (name, start_date, end_date, status, tenant_id)
- PayrollRun (period_id, status, total_gross, total_deductions, tenant_id)
- Payslip (run_id, employee_id, gross, deductions, net, tenant_id)
- PayslipLine (payslip_id, type, description, amount)
- SalaryComponent (name, type, calculation_method, tenant_id)
```

### Key Implementation: Payroll Processing

```python
# backend/src/modules/human_resources/services.py

class PayrollService:
    """Payroll processing with GL integration."""

    def process_payroll(
        self,
        period_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> PayrollRun:
        """
        Process payroll for period:
        1. Calculate gross for each employee
        2. Apply deductions (tax, benefits, etc.)
        3. Generate payslips
        4. Post to GL
        """

        period = PayrollPeriod.objects.get(
            id=period_id,
            tenant_id=tenant_id
        )

        if period.status != 'open':
            raise ValidationError(f"Period is {period.status}")

        # Get active employees
        employees = Employee.objects.filter(
            tenant_id=tenant_id,
            status='active'
        )

        with transaction.atomic():
            run = PayrollRun.objects.create(
                tenant_id=tenant_id,
                period=period,
                status='processing',
                created_by=user_id
            )

            total_gross = Decimal('0')
            total_deductions = Decimal('0')
            total_net = Decimal('0')

            for employee in employees:
                payslip = self._calculate_payslip(
                    run=run,
                    employee=employee,
                    period=period,
                    tenant_id=tenant_id
                )
                total_gross += payslip.gross
                total_deductions += payslip.total_deductions
                total_net += payslip.net

            run.total_gross = total_gross
            run.total_deductions = total_deductions
            run.total_net = total_net
            run.status = 'completed'
            run.save()

            # Post to GL
            self._post_payroll_to_gl(run, tenant_id, user_id)

            # Close period
            period.status = 'closed'
            period.save()

        return run

    def _calculate_payslip(
        self,
        run: PayrollRun,
        employee: Employee,
        period: PayrollPeriod,
        tenant_id: uuid.UUID
    ) -> Payslip:
        """Calculate individual payslip."""

        contract = employee.active_contract

        payslip = Payslip.objects.create(
            tenant_id=tenant_id,
            run=run,
            employee=employee,
            period_start=period.start_date,
            period_end=period.end_date
        )

        # Calculate gross
        gross = self._calculate_gross(employee, contract, period, tenant_id)

        # Calculate deductions
        deductions = self._calculate_deductions(employee, gross, tenant_id)

        # Create payslip lines
        for component, amount in gross.items():
            PayslipLine.objects.create(
                payslip=payslip,
                type='earning',
                description=component,
                amount=amount
            )

        for component, amount in deductions.items():
            PayslipLine.objects.create(
                payslip=payslip,
                type='deduction',
                description=component,
                amount=-amount
            )

        payslip.gross = sum(gross.values())
        payslip.total_deductions = sum(deductions.values())
        payslip.net = payslip.gross - payslip.total_deductions
        payslip.save()

        return payslip

    def _post_payroll_to_gl(
        self,
        run: PayrollRun,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID
    ):
        """
        Post payroll to GL.

        Journal Entry:
        - Debit: Salary Expense
        - Debit: Employer Tax Expense
        - Credit: Salaries Payable
        - Credit: Tax Payable
        - Credit: Benefits Payable
        """

        salary_expense = self._get_account(tenant_id, 'salary_expense')
        employer_tax = self._get_account(tenant_id, 'employer_tax_expense')
        salaries_payable = self._get_account(tenant_id, 'salaries_payable')
        tax_payable = self._get_account(tenant_id, 'payroll_tax_payable')

        # Aggregate by account
        lines = [
            {'account_id': salary_expense.id, 'debit': run.total_gross, 'credit': 0},
            {'account_id': salaries_payable.id, 'debit': 0, 'credit': run.total_net},
            {'account_id': tax_payable.id, 'debit': 0, 'credit': run.total_deductions},
        ]

        JournalEntryService().create_journal_entry(
            tenant_id=tenant_id,
            user_id=user_id,
            date=run.period.end_date,
            description=f"Payroll {run.period.name}",
            lines=lines
        )
```

---

## Week 27-28: Project Management Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `project_management` |
| Type | Core |
| Priority | P1 |
| Dependencies | HR, Accounting |
| Spec Location | `docs/modules/02-core/project-management/` |
| Timeline | 7-10 days |

### Key Entities

```python
# Project entities
- Project (name, code, customer_id, status, budget, tenant_id)
- ProjectPhase (project_id, name, start_date, end_date, status)
- Task (phase_id, name, assignee_id, status, estimated_hours, tenant_id)
- TimeEntry (task_id, employee_id, date, hours, billable, tenant_id)
- ProjectExpense (project_id, description, amount, date, status, tenant_id)
- ProjectBudget (project_id, category, amount, spent, tenant_id)
- Milestone (project_id, name, due_date, status, deliverables, tenant_id)
```

### Key Implementation: Project Costing

```python
# backend/src/modules/project_management/services.py

class ProjectCostingService:
    """Project costing and profitability analysis."""

    def calculate_project_cost(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> ProjectCostSummary:
        """Calculate total project cost."""

        project = Project.objects.get(
            id=project_id,
            tenant_id=tenant_id
        )

        # Calculate labor cost
        time_entries = TimeEntry.objects.filter(
            task__phase__project_id=project_id,
            tenant_id=tenant_id
        )

        labor_cost = Decimal('0')
        for entry in time_entries:
            hourly_rate = self._get_employee_cost_rate(entry.employee_id)
            labor_cost += entry.hours * hourly_rate

        # Calculate expenses
        expenses = ProjectExpense.objects.filter(
            project_id=project_id,
            tenant_id=tenant_id,
            status='approved'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Calculate revenue (for customer projects)
        revenue = Decimal('0')
        if project.customer_id:
            billable_entries = time_entries.filter(billable=True)
            for entry in billable_entries:
                billing_rate = self._get_billing_rate(project, entry.task)
                revenue += entry.hours * billing_rate

        total_cost = labor_cost + expenses
        profit = revenue - total_cost
        margin = (profit / revenue * 100) if revenue > 0 else Decimal('0')

        return ProjectCostSummary(
            project_id=project_id,
            labor_cost=labor_cost,
            expense_cost=expenses,
            total_cost=total_cost,
            revenue=revenue,
            profit=profit,
            margin=margin,
            budget=project.budget,
            budget_variance=project.budget - total_cost
        )

    def generate_project_invoice(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        billing_type: str = 'time_and_materials'
    ) -> Invoice:
        """Generate invoice from project time entries."""

        project = Project.objects.get(
            id=project_id,
            tenant_id=tenant_id
        )

        if not project.customer_id:
            raise ValidationError("Cannot invoice internal projects")

        # Get unbilled time entries
        entries = TimeEntry.objects.filter(
            task__phase__project_id=project_id,
            tenant_id=tenant_id,
            billable=True,
            invoiced=False
        )

        invoice = Invoice.objects.create(
            tenant_id=tenant_id,
            customer_id=project.customer_id,
            invoice_number=self._generate_invoice_number(tenant_id),
            date=timezone.now().date(),
            project=project,
            created_by=user_id
        )

        for entry in entries:
            billing_rate = self._get_billing_rate(project, entry.task)
            InvoiceLine.objects.create(
                invoice=invoice,
                description=f"{entry.task.name} - {entry.date}",
                quantity=entry.hours,
                unit_price=billing_rate
            )
            entry.invoiced = True
            entry.invoice = invoice
            entry.save()

        return invoice
```

---

## Week 28-30: Business Intelligence Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `business_intelligence` |
| Type | Core |
| Priority | P1 |
| Dependencies | All Core modules |
| Spec Location | `docs/modules/02-core/business-intelligence/` |
| Timeline | 10-12 days |

### Key Entities

```python
# BI entities
- Dashboard (name, layout, is_default, tenant_id)
- Widget (dashboard_id, type, config, position)
- Report (name, query, parameters, schedule, tenant_id)
- ReportExecution (report_id, status, output_format, output_path)
- KPI (name, formula, target, frequency, tenant_id)
- KPIValue (kpi_id, date, value, trend)
- DataSource (name, type, connection_config, tenant_id)
- SavedQuery (name, query, parameters, tenant_id)
```

### Key Implementation: KPI Engine

```python
# backend/src/modules/business_intelligence/services.py

class KPIService:
    """KPI calculation and tracking."""

    def calculate_kpi(
        self,
        kpi_id: uuid.UUID,
        tenant_id: uuid.UUID,
        as_of_date: date = None
    ) -> KPIValue:
        """Calculate KPI value."""

        kpi = KPI.objects.get(
            id=kpi_id,
            tenant_id=tenant_id
        )

        as_of_date = as_of_date or timezone.now().date()

        # Parse and execute formula
        value = self._execute_formula(kpi.formula, tenant_id, as_of_date)

        # Get previous value for trend
        previous = KPIValue.objects.filter(
            kpi_id=kpi_id,
            date__lt=as_of_date
        ).order_by('-date').first()

        trend = 'stable'
        if previous:
            change = value - previous.value
            if change > 0:
                trend = 'up'
            elif change < 0:
                trend = 'down'

        kpi_value = KPIValue.objects.create(
            kpi=kpi,
            date=as_of_date,
            value=value,
            trend=trend,
            against_target='above' if value >= kpi.target else 'below'
        )

        return kpi_value

    def _execute_formula(
        self,
        formula: str,
        tenant_id: uuid.UUID,
        as_of_date: date
    ) -> Decimal:
        """
        Execute KPI formula.

        Supported formulas:
        - revenue_mtd: Month-to-date revenue
        - ar_outstanding: Outstanding AR balance
        - inventory_value: Total inventory value
        - employee_count: Active employee count
        - avg_order_value: Average sales order value
        """

        formulas = {
            'revenue_mtd': self._calculate_revenue_mtd,
            'ar_outstanding': self._calculate_ar_outstanding,
            'inventory_value': self._calculate_inventory_value,
            'employee_count': self._calculate_employee_count,
            'avg_order_value': self._calculate_avg_order_value,
            'gross_margin': self._calculate_gross_margin,
        }

        if formula in formulas:
            return formulas[formula](tenant_id, as_of_date)

        raise ValueError(f"Unknown formula: {formula}")

    def _calculate_revenue_mtd(
        self,
        tenant_id: uuid.UUID,
        as_of_date: date
    ) -> Decimal:
        """Calculate month-to-date revenue."""

        month_start = as_of_date.replace(day=1)

        invoices = Invoice.objects.filter(
            tenant_id=tenant_id,
            status='posted',
            date__gte=month_start,
            date__lte=as_of_date
        )

        return invoices.aggregate(total=Sum('total'))['total'] or Decimal('0')


class DashboardService:
    """Dashboard management and data aggregation."""

    def get_executive_dashboard(
        self,
        tenant_id: uuid.UUID
    ) -> dict:
        """Get executive dashboard data."""

        today = timezone.now().date()
        month_start = today.replace(day=1)

        return {
            'revenue': {
                'mtd': self._get_kpi_value('revenue_mtd', tenant_id),
                'target': self._get_kpi_target('revenue_mtd', tenant_id),
                'trend': self._get_revenue_trend(tenant_id)
            },
            'orders': {
                'today': SalesOrder.objects.filter(
                    tenant_id=tenant_id,
                    date=today
                ).count(),
                'mtd': SalesOrder.objects.filter(
                    tenant_id=tenant_id,
                    date__gte=month_start
                ).count()
            },
            'ar_aging': self._get_ar_aging(tenant_id),
            'inventory_value': self._get_kpi_value('inventory_value', tenant_id),
            'top_customers': self._get_top_customers(tenant_id, limit=5),
            'top_products': self._get_top_products(tenant_id, limit=5),
            'cash_flow': self._get_cash_flow_summary(tenant_id)
        }
```

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] HR module operational (employees, payroll, leave)
- [ ] Project module operational (tasks, time, costing)
- [ ] BI module operational (dashboards, KPIs, reports)
- [ ] ≥90% test coverage per module
- [ ] Payroll-to-GL integration verified
- [ ] KPI calculations accurate
- [ ] All pre-commit hooks passing

### Core Modules Milestone

At end of Phase 12, Core layer is COMPLETE:
- ✅ CRM
- ✅ Accounting & Finance
- ✅ Sales Management
- ✅ Purchase Management
- ✅ Inventory Management
- ✅ Human Resources
- ✅ Project Management
- ✅ Business Intelligence

**Total Core Modules:** 8 operational

---

## Post-Core Assessment

### Ready for Phase 13+ (Industry Modules)

Before proceeding to Industry modules:
- [ ] All 8 Core modules operational
- [ ] Cross-module workflows tested
- [ ] Performance benchmarks met
- [ ] Security audit complete
- [ ] Architecture Board sign-off

### Industry Module Prioritization

Based on customer demand and market analysis:
1. Manufacturing
2. Healthcare
3. Retail
4. Professional Services
5. Financial Services

---

## Document Status

**Status:** BLOCKED (Awaiting Phase 11)  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 13+ (Industry Modules - TBD)

---

