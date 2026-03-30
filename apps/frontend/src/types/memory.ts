export interface UserMemorySettings {
  user_id: string;
  memory_enabled: boolean;
  instructions_enabled: boolean;
  allow_explicit_memory: boolean;
  allow_inferred_memory: boolean;
  allow_chat_history_reference: boolean;
  default_memory_mode: string;
  created_at: string;
  updated_at: string;
}

export interface PersonalMemoryEntry {
  id: string;
  user_id: string;
  thread_id: string | null;
  scope_type: string;
  source_type: string;
  status: string;
  category: string;
  title: string;
  content_text: string;
  confidence: number | null;
  salience: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export type PersonalizationInstructionType = 'response_style' | 'user_profile';

export interface PersonalizationInstruction {
  id: string;
  user_id: string;
  instruction_type: PersonalizationInstructionType;
  title: string;
  content_text: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
