export type RoleName = "customer" | "operator" | "admin";

export type Role = {
  id: number;
  name: RoleName | string;
  description: string;
};
export type User = {
  id: number;
  full_name: string;
  email: string;
  locale: string;
  department?: string | null;
  title?: string | null;
  is_active: boolean;
  role: Role;
};
export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};
export type ChatSessionSummary = {
  id: number;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
};
export type AppointmentInMessage = {
  confirmation_code: string;
  department: string;
  scheduled_at: string;
  location: string;
  purpose?: string | null;
  status: string;
};
export type IntelligenceActivityEvent = {
  label: string;
  status: "completed" | "in_progress" | "pending" | "blocked" | string;
};
export type IntelligenceActivity = {
  type: "external_outreach";
  job_id: number;
  company: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  source_url?: string | null;
  source_kind?: string | null;
  source_label?: string | null;
  confidence: number;
  status: string;
  failure_reason?: string | null;
  extracted_terms?: {
    company?: string;
    location?: string | null;
    purpose?: string | null;
    search_query?: string;
    entity_type?: "company" | "category" | string;
  };
  events: IntelligenceActivityEvent[];
};
export type ChatMessage = {
  id: number;
  sender: "user" | "assistant" | "system" | "tool";
  content: string;
  language: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  appointment?: AppointmentInMessage | null;
};
export type ChatSessionDetail = {
  id: number;
  title: string;
  status: string;
  workflow_state: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};
export type AgentReply = {
  message: string;
  language: string;
  outcome: string;
  confirmation_card?: ConfirmationCard | null;
};
export type SendMessageResponse = {
  session: ChatSessionDetail;
  assistant_reply: AgentReply;
};
export type ConfirmationCard = {
  type: "appointment_confirmation";
  confirmation_code: string;
  department: string;
  scheduled_at: string;
  location: string;
  contact_phone: string;
  status: string;
};
export type AuditLog = {
  id: number;
  timestamp: string;
  user_id?: number | null;
  session_id?: number | null;
  action_type: string;
  tool_name?: string | null;
  result_status: string;
  success: boolean;
  explanation: string;
  details?: Record<string, unknown> | null;
  created_at: string;
};
export type Metrics = {
  active_sessions: number;
  confirmed_appointments: number;
  audit_events_today: number;
  completion_rate: number;
};
export type ProviderCapability = {
  active_provider?: string;
  available_providers?: string[];
  [key: string]: unknown;
};
export type AICapabilities = {
  llm: ProviderCapability;
  voice: {
    stt: ProviderCapability;
    tts: ProviderCapability;
  };
  sms?: {
    configured_provider: string;
    active_provider: string;
    real_delivery: boolean;
    misconfigured: boolean;
  };
  [key: string]: unknown;
};
export type QualityReport = {
  score: number;
  grade: string;
  metrics: {
    automated_scenarios: number;
    recent_failures: number;
    [key: string]: unknown;
  };
  recommendations: Array<{ title: string; [key: string]: unknown }>;
  llm: ProviderCapability;
  voice: {
    stt: ProviderCapability;
    tts: ProviderCapability;
  };
  [key: string]: unknown;
};

export type ClinicalPilotMetric = {
  id: string;
  label: string;
  value: number;
  target?: number | null;
  unit: string;
  passed?: boolean | null;
};

export type ClinicalPilotMetrics = {
  window_days: number;
  totals: Record<string, number>;
  metrics: ClinicalPilotMetric[];
  ready_for_pilot: boolean;
};

export type ClinicalPilotWeeklyReport = {
  window_days: number;
  generated_at: string;
  summary: Record<string, unknown>;
  markdown: string;
};

export type ClinicalPilotLaunchChecklist = {
  window_days: number;
  ready_for_launch: boolean;
  checklist: Array<{
    id: string;
    label: string;
    status: "pass" | "risk" | "manual" | "no_data" | string;
    detail: string;
  }>;
  rollback_plan: string[];
  incident_response: string[];
};

export type ClinicalVoiceQARunInput = {
  tester: string;
  device: string;
  browser: string;
  audio_condition: string;
  voice_mode: string;
  scenario: string;
  mic_permission_seconds?: number | null;
  first_assistant_audio_seconds?: number | null;
  transcript_correct: boolean;
  transcript_shown: boolean;
  retry_count: number;
  completed_under_60s: boolean;
  appointment_created: boolean;
  operator_intervention: boolean;
  emergency_guidance_shown?: boolean | null;
  severity: "pass" | "minor" | "major" | "blocking";
  notes?: string | null;
  metadata_json?: Record<string, unknown>;
};

export type ClinicalVoiceQARun = ClinicalVoiceQARunInput & {
  id: number;
  clinic_id: number;
  created_at: string;
};

export type ClinicalVoiceQAReport = {
  summary: Record<string, number | boolean>;
  runs: ClinicalVoiceQARun[];
};

export type Appointment = {
  id: number;
  confirmation_code: string;
  department: string;
  purpose: string;
  contact_phone: string;
  notes?: string | null;
  language: string;
  status: string;
  scheduled_at: string;
  location: string;
  created_at: string;
  user_name?: string | null;
  user_id?: number | null;
};

export type Organization = {
  id: number;
  name: string;
  domain?: string | null;
};
export type EnterpriseDepartment = {
  id: number;
  organization_id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
};
export type EnterpriseCustomer = {
  id: number;
  organization_id: number;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  external_ref?: string | null;
};
export type EnterpriseAgent = {
  id: number;
  user_id: number;
  department_id?: number | null;
  display_name: string;
  availability_status: string;
};
export type EnterpriseTicket = {
  id: number;
  session_id?: number | null;
  customer: EnterpriseCustomer;
  department?: EnterpriseDepartment | null;
  assigned_agent?: EnterpriseAgent | null;
  intent: string;
  description: string;
  status: string;
  priority: string;
  confidence: number;
  handoff_package?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type EnterpriseSessionSummary = {
  id: number;
  chat_session_id: number;
  customer: EnterpriseCustomer;
  department?: EnterpriseDepartment | null;
  status: string;
  intent?: string | null;
  confidence: number;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
};
export type EnterpriseSessionDetail = EnterpriseSessionSummary & {
  messages: ChatMessage[];
  handoff_package?: Record<string, unknown> | null;
};
export type EnterpriseMetrics = {
  organization: Organization;
  total_tickets: number;
  open_tickets: number;
  high_priority_tickets: number;
  sla_breached: number;
  avg_confidence: number;
  active_sessions: number;
  escalations: number;
  appointments: number;
};
export type EnterpriseOverview = {
  metrics: EnterpriseMetrics;
  departments: EnterpriseDepartment[];
  agents: EnterpriseAgent[];
  tickets: EnterpriseTicket[];
  sessions: EnterpriseSessionSummary[];
};
export type EnterpriseDecision = {
  intent: string;
  department?: EnterpriseDepartment | null;
  confidence: number;
  action: string;
  ticket?: EnterpriseTicket | null;
  appointment?: Appointment | null;
  handoff_package?: Record<string, unknown> | null;
  explanation: string;
};
export type EnterpriseMessageResponse = {
  session: EnterpriseSessionDetail;
  assistant_message: string;
  decision: EnterpriseDecision;
};
export type KnowledgeArticle = {
  id: number;
  organization_id: number;
  title: string;
  content: string;
  tags: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
export type KnowledgeSearchResult = KnowledgeArticle & {
  score: number;
};

export type ClinicalPatient = {
  id: number;
  clinic_id: number;
  full_name?: string | null;
  phone: string;
  language: string;
  source: string;
  created_at: string;
  updated_at: string;
};
export type ClinicalMessage = {
  id: number;
  conversation_id: number;
  sender: "patient" | "assistant" | "operator" | "system";
  content: string;
  language: string;
  intent?: string | null;
  confidence_score?: number | null;
  external_message_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};
export type ClinicalConversationSummary = {
  id: number;
  clinic_id: number;
  patient: ClinicalPatient;
  channel: string;
  status: string;
  language: string;
  intent?: string | null;
  confidence_score?: number | null;
  persona_name?: string | null;
  last_urgency?: string | null;
  doctor_summary?: string | null;
  possible_conditions?: Array<Record<string, unknown>>;
  appointment_draft?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  doctor_inbox: boolean;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
};
export type ClinicalConversationDetail = ClinicalConversationSummary & {
  messages: ClinicalMessage[];
};
export type ShadowReview = {
  id: number;
  clinic_id: number;
  conversation_id: number;
  patient_message_id: number;
  assigned_doctor_id?: number | null;
  assigned_doctor_name?: string | null;
  assigned_doctor_specialty?: string | null;
  draft_reply: string;
  intent: string;
  confidence_score: number;
  risk_reason: string;
  status: string;
  persona_name?: string | null;
  channel?: string | null;
  final_reply?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type ClinicalMetrics = {
  clinic_name: string;
  conversations_today: number;
  total_conversations: number;
  pending_shadow_reviews: number;
  triage_reviews: number;
  emergency_reviews: number;
  same_day_reviews: number;
  doctor_inbox_count: number;
  phone_calls_today: number;
  whatsapp_threads_today: number;
  auto_reply_rate: number;
  appointments_pending: number;
  reminders_due: number;
  frustration_events: number;
};
export type ClinicalViewer = {
  clinic_role: string;
  doctor_id?: number | null;
  doctor_name?: string | null;
  specialty?: string | null;
};
export type ClinicalOverview = {
  viewer?: ClinicalViewer;
  metrics: ClinicalMetrics;
  conversations: ClinicalConversationSummary[];
  doctor_inbox: ClinicalConversationSummary[];
  shadow_reviews: ShadowReview[];
};
export type ClinicalComplianceProfile = {
  clinic_id: number;
  clinic_name: string;
  data_residency_default: string;
  external_transfer_allowed: boolean;
  processor_inventory: Array<Record<string, unknown>>;
  production_modes: Array<Record<string, unknown>>;
  mandatory_controls: string[];
  blocked_by_default: string[];
  operator_review_triggers: string[];
  retention_policy?: Record<string, unknown> | null;
};
export type ClinicalPatentDossier = {
  working_title: string;
  technical_field: string;
  problem: string;
  solution_summary: string;
  candidate_independent_claims: string[];
  candidate_dependent_claims: string[];
  figures_to_prepare: string[];
  evidence_to_preserve: string[];
  next_actions: string[];
};
export type ClinicalSlotAppointment = {
  id: string;
  time: string;
  patient_name: string;
  doctor: string;
  branch: string;
  department: string;
  date_label: string;
  phone: string;
  status: "confirmed" | "pending" | string;
  status_label: string;
};
export type ClinicalProcedure = {
  id: number;
  name: string;
  code: string | null;
  tooth: string | null;
  status: "planned" | "in_progress" | "completed" | "cancelled" | string;
  notes: string | null;
  sort_order: number;
  performed_by_doctor_id: number | null;
  started_at: string | null;
  completed_at: string | null;
};
export type ClinicalAppointmentRow = {
  id: number;
  patient_id: number;
  patient_name: string | null;
  patient_phone: string | null;
  conversation_id: number | null;
  assigned_doctor_id: number | null;
  department: string;
  physician_name: string | null;
  branch_name: string | null;
  starts_at: string | null;
  ends_at: string | null;
  duration_minutes: number;
  visit_reason: string | null;
  status: "pending" | "confirmed" | "cancelled" | string;
  notes: string | null;
  procedures: ClinicalProcedure[];
  created_at: string;
};
export type ClinicalAppointment = {
  id: number;
  clinic_id: number;
  patient_id: number;
  conversation_id?: number | null;
  doctor_id?: number | null;
  slot_id?: number | null;
  assigned_doctor_id?: number | null;
  assigned_doctor_name?: string | null;
  department: string;
  starts_at?: string | null;
  ends_at?: string | null;
  duration_minutes: number;
  visit_reason?: string | null;
  status: string;
  notes?: string | null;
  doctor_name?: string | null;
  metadata_json?: Record<string, unknown> | null;
  procedures: ClinicalProcedure[];
  created_at: string;
  updated_at: string;
};
export type ClinicalSlotItem = {
  id: string;
  department: string;
  doctor: string;
  date_label: string;
  time_range: string;
  capacity: number;
  booked: number;
  open: number;
  status: "available" | "limited" | "full" | string;
  next_available: string;
  waitlist_count: number;
  appointments?: ClinicalSlotAppointment[];
};
export type ClinicalSlotBoard = {
  summary: {
    clinic_mode: string;
    occupancy_rate: number;
    full_departments: number;
    next_open_slot: string;
    waitlist_total: number;
  };
  schedule: ClinicalSlotItem[];
  acceptance_rules: Array<{ rule: string; result: string }>;
  test_scenarios: Array<{ label: string; message: string; expected_action: string; expected_result: string }>;
};
export type WebhookIngestionResponse = {
  ok: boolean;
  clinic_id: number;
  patient_id: number;
  conversation_id: number;
  message_id: number;
  action: string;
  reply?: string | null;
  shadow_review_id?: number | null;
  appointment_id?: number | null;
  intent?: string | null;
  confidence?: number | null;
  risk?: "low" | "medium" | "high" | null;
  requires_human_review?: boolean;
  persona_name?: string | null;
  risk_reason?: string | null;
};
export type ClinicalPersona = {
  id: "selin" | "arzu" | "can";
  display_name: string;
  role: string;
  voice: string;
  tone: string;
  specialty: string;
  safety_rule: string;
};
export type ClinicDoctor = {
  id: number;
  clinic_id: number;
  branch_id?: number | null;
  full_name: string;
  email: string;
  specialty: string;
  title: string;
  bio?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
export type ClinicDoctorSlot = {
  id: number;
  doctor_id: number;
  clinic_id: number;
  start_time: string;
  end_time: string;
  is_booked: boolean;
  is_blocked: boolean;
  doctor_name?: string | null;
  specialty?: string | null;
};
