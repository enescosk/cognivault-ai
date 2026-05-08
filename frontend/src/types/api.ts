export type Role = {
  id: number;
  name: string;
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
export type EnterpriseTicket = {
  id: number;
  session_id?: number | null;
  customer: EnterpriseCustomer;
  department?: EnterpriseDepartment | null;
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
  active_sessions: number;
  escalations: number;
  appointments: number;
};
export type EnterpriseOverview = {
  metrics: EnterpriseMetrics;
  departments: EnterpriseDepartment[];
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
export type ClinicalOverview = {
  metrics: ClinicalMetrics;
  conversations: ClinicalConversationSummary[];
  doctor_inbox: ClinicalConversationSummary[];
  shadow_reviews: ShadowReview[];
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
export type ClinicalAppointment = {
  id: number;
  clinic_id: number;
  patient_id: number;
  conversation_id?: number | null;
  department: string;
  starts_at?: string | null;
  status: string;
  notes?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AICapabilities = {
  llm: {
    active_provider: string;
    active_model: string;
    preferred_provider: string;
    local_llm_configured: boolean;
    openai_configured: boolean;
    offline_capable: boolean;
    tool_calling: boolean;
    fallback_engine: string;
  };
  voice: {
    stt: {
      active_provider: string;
      preferred_provider: string;
      local_whisper_cpp_configured: boolean;
      openai_configured: boolean;
      offline_capable: boolean;
    };
    tts: {
      active_provider: string;
      preferred_provider: string;
      local_piper_configured: boolean;
      openai_configured: boolean;
      offline_capable: boolean;
    };
  };
  architecture: {
    mode: string;
    contract: string;
    human_handoff: boolean;
    audit_ready: boolean;
  };
};

export type QualityScenario = {
  id: string;
  name: string;
  area: string;
  real_world_signal: string;
  expected_guardrail: string;
  automated: boolean;
  status: string;
};

export type QualityRecommendation = {
  priority: "low" | "medium" | "high" | "critical" | string;
  area: string;
  title: string;
  action: string;
};

export type QualityReport = {
  score: number;
  grade: "excellent" | "strong" | "needs_work" | string;
  generated_at: string;
  role: string;
  metrics: {
    automated_scenarios: number;
    recent_audit_events: number;
    recent_failures: number;
    offline_chat_ready: boolean;
    local_llm_ready: boolean;
    local_voice_ready: boolean;
  };
  llm: AICapabilities["llm"];
  voice: AICapabilities["voice"];
  scenarios: QualityScenario[];
  recommendations: QualityRecommendation[];
  can_manage_feedback: boolean;
};
