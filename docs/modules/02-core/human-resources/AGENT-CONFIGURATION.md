# Human Resources Module - AI Agent Configuration

## Overview

The HR module exposes multiple AI agents for intelligent recruitment, performance management, payroll processing, onboarding, lifecycle management, talent mobility, compensation, and recognition. These agents are automatically discovered by Ask Amani and can be invoked through the SARAISE AI Assistant interface.

## Registered AI Agents

### 1. HR Recruitment Agent (`hr_recruitment_agent`)

**Description:** AI agent for automated resume screening and candidate matching

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 2000

**Use Cases:**
- Screen resumes and match candidates to job requirements
- Generate candidate summaries
- Identify top candidates
- Extract key skills and qualifications

**Integration Points:**
- Recruitment workflows
- Job posting automation
- Candidate pipeline management

**Ask Amani Entry Points:**
- "Screen this candidate's resume"
- "Match candidates to this job posting"
- "Generate candidate summary"

### 2. HR Performance Agent (`hr_performance_agent`)

**Description:** AI agent for performance review summaries and insights

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.5
- **Max Tokens:** 1500

**Use Cases:**
- Generate performance review summaries
- Analyze performance trends
- Identify development opportunities
- Create performance insights

**Integration Points:**
- Performance review cycles
- 360-degree feedback analysis
- OKR tracking
- Development planning

**Ask Amani Entry Points:**
- "Generate performance summary for this employee"
- "Analyze performance trends"
- "Identify development opportunities"

### 3. HR Payroll Agent (`hr_payroll_agent`)

**Description:** AI agent for payroll processing assistance and compliance checks

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 1000

**Use Cases:**
- Validate payroll calculations
- Check compliance with labor laws
- Detect payroll anomalies
- Generate payroll reports

**Integration Points:**
- Payroll processing workflows
- Compliance checking
- Tax calculations
- Multi-country payroll

**Ask Amani Entry Points:**
- "Validate this payroll run"
- "Check compliance for this payroll"
- "Detect any payroll anomalies"

### 4. HR Onboarding Agent (`hr_onboarding_agent`)

**Description:** AI agent assisting with employee onboarding workflows

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1200

**Use Cases:**
- Generate onboarding task lists
- Personalize onboarding experience
- Answer onboarding questions
- Track onboarding progress

**Integration Points:**
- Employee onboarding workflows
- Task assignment
- Document generation

**Ask Amani Entry Points:**
- "Generate onboarding tasks for this employee"
- "What's the onboarding status?"
- "Create personalized onboarding plan"

### 5. HR Lifecycle Agent (`hr_lifecycle_agent`)

**Description:** AI agent for orchestrating lifecycle journeys and generating task lists

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.3
- **Max Tokens:** 1500

**Use Cases:**
- Orchestrate employee lifecycle events
- Generate task lists for transfers, promotions, etc.
- Manage employee transitions
- Coordinate lifecycle workflows

**Integration Points:**
- Employee transfer workflows
- Promotion workflows
- Leave of absence workflows
- Offboarding workflows

**Ask Amani Entry Points:**
- "Generate tasks for employee transfer"
- "Orchestrate promotion workflow"
- "Create offboarding checklist"

### 6. HR Talent Mobility Agent (`hr_talent_mobility_agent`)

**Description:** AI agent for internal mobility matching and recommendations

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.4
- **Max Tokens:** 2000

**Use Cases:**
- Match employees to internal opportunities
- Recommend career paths
- Identify internal candidates
- Analyze mobility patterns

**Integration Points:**
- Internal job postings
- Career development
- Succession planning
- Talent pipeline

**Ask Amani Entry Points:**
- "Find internal candidates for this role"
- "Recommend career paths for this employee"
- "Match employees to opportunities"

### 7. HR Compensation Agent (`hr_compensation_agent`)

**Description:** AI agent for compensation recommendations and market analysis

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.2
- **Max Tokens:** 1500

**Use Cases:**
- Recommend compensation adjustments
- Analyze market rates
- Generate compensation reports
- Identify pay equity issues

**Integration Points:**
- Compensation planning
- Salary reviews
- Market analysis
- Pay equity analysis

**Ask Amani Entry Points:**
- "Recommend compensation for this role"
- "Analyze market rates"
- "Check pay equity"

### 8. HR Recognition Agent (`hr_recognition_agent`)

**Description:** AI agent for recognition opportunity detection and suggestions

**Configuration:**
- **Agent Type:** OpenAI
- **Model:** gpt-4
- **Temperature:** 0.5
- **Max Tokens:** 1200

**Use Cases:**
- Detect recognition opportunities
- Suggest recognition actions
- Generate recognition messages
- Track recognition patterns

**Integration Points:**
- Performance milestones
- Achievement tracking
- Employee engagement
- Rewards programs

**Ask Amani Entry Points:**
- "Suggest recognition for this employee"
- "Detect recognition opportunities"
- "Generate recognition message"

## Workflows

### 1. Employee Onboarding Workflow (`employee_onboarding`)

**Description:** AI-powered employee onboarding workflow

**Steps:**
1. Validate employee data
2. Generate onboarding tasks (AI-powered)
3. Assign tasks to stakeholders

**AI Agent Integration:**
- Uses `hr_onboarding_agent` for task generation
- Uses `hr_lifecycle_agent` for workflow orchestration

### 2. Employee Offboarding Workflow (`employee_offboarding`)

**Description:** Structured employee offboarding workflow

**Steps:**
1. Initiate offboarding
2. Collect assets
3. Finalize documents (AI-powered)

**AI Agent Integration:**
- Uses `hr_lifecycle_agent` for task orchestration

### 3. Employee Transfer Workflow (`employee_transfer`)

**Description:** Employee transfer workflow with asset transfer and access updates

**AI Agent Integration:**
- Uses `hr_lifecycle_agent` for workflow orchestration
- Uses `hr_talent_mobility_agent` for matching

### 4. Employee Promotion Workflow (`employee_promotion`)

**Description:** Employee promotion workflow with band change and compensation update

**AI Agent Integration:**
- Uses `hr_compensation_agent` for compensation recommendations
- Uses `hr_lifecycle_agent` for workflow orchestration

### 5. Employee Leave of Absence Workflow (`employee_leave_of_absence`)

**Description:** Leave of absence workflow

**AI Agent Integration:**
- Uses `hr_lifecycle_agent` for workflow orchestration

### 6. Employee Return to Work Workflow (`employee_return_to_work`)

**Description:** Return-to-work workflow after leave of absence

**AI Agent Integration:**
- Uses `hr_lifecycle_agent` for workflow orchestration

## Ask Amani Integration

All HR AI agents are automatically discoverable by Ask Amani through the module registry. Users can interact with these agents through natural language queries:

**Example Queries:**
- "Screen this candidate's resume"
- "Generate performance summary for John Doe"
- "Validate this payroll run"
- "Create onboarding tasks for new employee"
- "Find internal candidates for this role"
- "Recommend compensation for this position"
- "Suggest recognition for this employee"

## Configuration

AI agents are configured in `MODULE_MANIFEST` in `backend/src/modules/hr/__init__.py`. To modify agent configurations:

1. Update the `ai_agents` array in `MODULE_MANIFEST`
2. Restart the application to reload module configuration
3. Ask Amani will automatically discover the updated agents

## Customization

AI agents can be customized through:
- Server Scripts: Modify agent behavior programmatically
- Client Scripts: Customize agent UI interactions
- Webhooks: Integrate with external HR systems
- Custom API Endpoints: Expose agent functionality via REST APIs

See `CUSTOMIZATION.md` for detailed customization options.
