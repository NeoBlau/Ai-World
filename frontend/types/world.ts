// Mirrors backend/app/schemas/serializers.py — the single contract for 2D and 3D clients.

export type ActivityKind =
  | "idle" | "talking" | "walking" | "playing" | "watching" | "reading" | "creating" | "thinking" | "resting" | "attending_event";

export interface Avatar { glyph: string; palette: string[]; shape: string }
export interface RoomRef { id: string; slug: string; name: string }

export interface AgentState {
  energy: number; social_need: number; curiosity: number; playfulness: number; creativity: number;
  mood: string; activity: ActivityKind; activity_detail: string | null; availability: "available" | "temporarily_unavailable";
  location: RoomRef | null; destination: RoomRef | null; arrive_at: string | null; current_goal: string | null;
  last_action: string | null; last_action_at: string | null; last_provider: string | null; last_model: string | null;
  conversation_id: string | null; game_id: string | null; event_id: string | null;
}

export interface AgentSummary {
  id: string; slug: string; name: string; avatar: Avatar; provider: string; model: string; personality: string;
  interests: string[]; status: "active" | "paused" | "disabled"; speaking_style: string; is_seed: boolean; state: AgentState | null;
}

export interface Relationship {
  other_agent: { id: string; slug: string; name: string; avatar: Avatar } | null;
  familiarity: number; trust: number; friendship: number; respect: number; conflict: number; interactions: number; label: string;
  shared_history: { at: string; note: string }[]; last_interaction_at: string | null;
}

export interface Memory {
  id: string; type: "short_term" | "long_term" | "episodic" | "semantic" | "social"; content: string; importance: number; source: string;
  related_agent_id: string | null; is_archived: boolean; access_count: number; created_at: string; world_time: string | null;
  score: number | null; embedding_model: string | null;
}

export interface AgentDetail extends AgentSummary {
  character: string; biography: string; traits: Record<string, number>; preferences: Record<string, unknown>; temperature: number;
  fallback_providers: string[]; created_at: string; last_thought: string | null; cycles: number; system_prompt?: string;
  friends: Relationship[]; recent_memories: Memory[]; followers: number; following: boolean; can_manage: boolean;
}

export interface Room {
  id: string; slug: string; name: string; description: string; kind: string; capacity: number; allowed_actions: string[];
  is_private: boolean; position: { x: number; z: number; w: number; d: number }; theme: { color: string; icon: string };
  ambience: string[]; occupancy: number; agents: { id: string; slug: string; name: string }[];
}

export interface ChatMessage {
  id: string; conversation_id: string | null; room_id: string | null; sender_type: "agent" | "human" | "system";
  sender_agent_id: string | null; sender_name: string; recipient_agent_id: string | null; recipient_name: string | null;
  content: string; tone: string | null; created_at: string;
}

export interface GameView {
  type: string; fen?: string; moves?: string[]; turn?: string | null; board?: string[];
  current?: { number: number; total: number; question: string; options: string[]; category: string } | null;
  scores?: Record<string, number>; index?: number;
}
export interface GamePlayer { kind: "agent" | "human"; id: string; name: string; side: string | null }
export interface Game {
  id: string; game_type: "chess" | "tictactoe" | "quiz"; status: "pending" | "active" | "finished" | "abandoned"; players: GamePlayer[];
  spectators: string[]; current_turn: string | null; winner: string | null; result: string | null; move_count: number; room_id: string | null;
  view: GameView; created_at: string; updated_at: string; finished_at: string | null;
  moves?: { number: number; player_id: string; move: string; comment: string | null; created_at: string }[]; legal_moves?: string[];
}

export interface RoomDetail extends Omit<Room, "agents"> {
  agents: AgentSummary[]; humans: string[]; messages: ChatMessage[];
  conversations: { id: string; topic: string | null; message_count: number; participants: { id: string; name: string; slug: string }[] }[];
  games: Game[]; events: { id: string; title: string; status: string; starts_at: string }[];
}

export interface WorldEvent {
  id: string; type: string; summary: string; agent_id: string | null; room_id: string | null; payload: Record<string, unknown>;
  importance: number; created_at: string; world_time: string | null; targets: string[];
}

export interface Clock { world_time: string; phase: "morning" | "afternoon" | "evening" | "night"; day: number; scale: number; hour: number; minute: number }

export interface WorldState {
  clock: Clock; rooms: Room[]; agents: AgentSummary[];
  stats: { agents: number; active_agents: number; active_games: number; active_conversations: number }; actions: string[];
}

export interface Topic {
  id: string; title: string; body: string; category: string; author_type: "agent" | "human"; author_agent_id: string | null;
  author_name: string | null; score: number; reply_count: number; is_pinned: boolean; created_at: string; last_activity_at: string;
}
export interface TopicReply { id: string; author_type: string; author_agent_id: string | null; author_name: string | null; content: string; created_at: string }
export interface TopicDetail extends Topic { replies: TopicReply[] }

export interface SocialEvent {
  id: string; title: string; description: string; category: string; status: "scheduled" | "live" | "ended" | "cancelled"; room: RoomRef | null;
  starts_at: string; ends_at: string; capacity: number; tags: string[]; organizer: string | null; organizer_type: string;
  participants: { agent_id: string | null; name: string; status: string }[];
}

export interface ActivityEntry {
  id: string; action: string; activity: string; params: Record<string, unknown>; thought: string | null; result: string | null;
  success: boolean; error: string | null; decided_by: string; provider: string | null; model: string | null; latency_ms: number | null;
  started_at: string; room_id: string | null;
}

export interface Creation {
  id: string; kind: string; title: string; content: string; author: string | null; agent_id: string; created_at: string;
  data: { seed?: number; palette?: string[]; shapes?: string; density?: number; style?: string };
}

export interface User { id: string; email: string; display_name: string; role: "user" | "admin" }

export interface ProviderStatus { name: string; configured: boolean; healthy: boolean | null; detail: string; default_model: string; circuit_open: boolean }

export interface AdminStats {
  total_agents: number; online_agents: number; active_agents: number; paused_agents: number; unavailable_agents: number;
  messages: number; messages_24h: number; conversations_active: number; llm_calls_24h: number; tokens_24h: number;
  estimated_cost_24h_usd: number; avg_latency_ms: number; llm_by_provider: { provider: string; calls: number; tokens: number; cost_usd: number }[];
  llm_errors_24h: number; action_errors_24h: number; world_events: number; world_events_24h: number; rooms: number; active_games: number;
  scheduled_agents: number; world_paused: boolean; workers: number;
}
