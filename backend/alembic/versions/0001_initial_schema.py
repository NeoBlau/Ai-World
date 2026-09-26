"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-09-26 12:08:04.484256
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('agents',
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('avatar', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('system_prompt', sa.Text(), nullable=False),
    sa.Column('fallback_providers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('personality', sa.String(length=200), nullable=False),
    sa.Column('character', sa.Text(), nullable=False),
    sa.Column('traits', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('interests', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('biography', sa.Text(), nullable=False),
    sa.Column('speaking_style', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('is_seed', sa.Boolean(), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_slug'), 'agents', ['slug'], unique=True)
    op.create_index(op.f('ix_agents_status'), 'agents', ['status'], unique=False)
    op.create_table('books',
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('author', sa.String(length=120), nullable=False),
    sa.Column('topics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('passages', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('times_read', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('current_room_id', sa.UUID(), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('world_settings',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('invitations',
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('from_agent_id', sa.UUID(), nullable=True),
    sa.Column('from_user_id', sa.UUID(), nullable=True),
    sa.Column('to_agent_id', sa.UUID(), nullable=False),
    sa.Column('ref_id', sa.UUID(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['from_agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_invitations_to_status', 'invitations', ['to_agent_id', 'status'], unique=False)
    op.create_table('llm_calls',
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_llm_calls_agent_id'), 'llm_calls', ['agent_id'], unique=False)
    op.create_index('ix_llm_calls_created', 'llm_calls', ['created_at'], unique=False)
    op.create_table('relationships',
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('other_agent_id', sa.UUID(), nullable=False),
    sa.Column('familiarity', sa.Float(), nullable=False),
    sa.Column('trust', sa.Float(), nullable=False),
    sa.Column('friendship', sa.Float(), nullable=False),
    sa.Column('respect', sa.Float(), nullable=False),
    sa.Column('conflict', sa.Float(), nullable=False),
    sa.Column('interactions', sa.Integer(), nullable=False),
    sa.Column('shared_history', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_interaction_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['other_agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('agent_id', 'other_agent_id', name='uq_relationship_pair')
    )
    op.create_index(op.f('ix_relationships_agent_id'), 'relationships', ['agent_id'], unique=False)
    op.create_index(op.f('ix_relationships_other_agent_id'), 'relationships', ['other_agent_id'], unique=False)
    op.create_table('rooms',
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('allowed_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_private', sa.Boolean(), nullable=False),
    sa.Column('access_list', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=True),
    sa.Column('owner_agent_id', sa.UUID(), nullable=True),
    sa.Column('position', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('theme', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ambience', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rooms_slug'), 'rooms', ['slug'], unique=True)
    op.create_table('topics',
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('author_type', sa.String(length=10), nullable=False),
    sa.Column('author_agent_id', sa.UUID(), nullable=True),
    sa.Column('author_user_id', sa.UUID(), nullable=True),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('reply_count', sa.Integer(), nullable=False),
    sa.Column('is_pinned', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['author_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_topics_author_agent_id'), 'topics', ['author_agent_id'], unique=False)
    op.create_index('ix_topics_category_activity', 'topics', ['category', 'last_activity_at'], unique=False)
    op.create_table('user_follows',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'agent_id', name='uq_user_follow')
    )
    op.create_index(op.f('ix_user_follows_agent_id'), 'user_follows', ['agent_id'], unique=False)
    op.create_index(op.f('ix_user_follows_user_id'), 'user_follows', ['user_id'], unique=False)
    op.create_table('activities',
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('activity', sa.String(length=30), nullable=False),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('thought', sa.Text(), nullable=True),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=True),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_activities_agent_started', 'activities', ['agent_id', 'started_at'], unique=False)
    op.create_table('agent_memories',
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('memory_type', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('embedding_model', sa.String(length=80), nullable=True),
    sa.Column('importance', sa.Float(), nullable=False),
    sa.Column('related_agent_id', sa.UUID(), nullable=True),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('access_count', sa.Integer(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('world_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['related_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_memories_agent_id'), 'agent_memories', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_memories_is_archived'), 'agent_memories', ['is_archived'], unique=False)
    op.create_index('ix_memories_agent_related', 'agent_memories', ['agent_id', 'related_agent_id'], unique=False)
    op.create_index('ix_memories_agent_type_created', 'agent_memories', ['agent_id', 'memory_type', 'created_at'], unique=False)
    op.create_table('conversations',
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('topic', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('started_by_agent_id', sa.UUID(), nullable=True),
    sa.Column('started_by_user_id', sa.UUID(), nullable=True),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['started_by_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['started_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_room_status', 'conversations', ['room_id', 'status'], unique=False)
    op.create_table('creations',
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('is_public', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_creations_agent_id'), 'creations', ['agent_id'], unique=False)
    op.create_table('events',
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('organizer_type', sa.String(length=10), nullable=False),
    sa.Column('organizer_agent_id', sa.UUID(), nullable=True),
    sa.Column('organizer_user_id', sa.UUID(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['organizer_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organizer_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_status_starts', 'events', ['status', 'starts_at'], unique=False)
    op.create_table('games',
    sa.Column('game_type', sa.String(length=20), nullable=False),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('players', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('spectators', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('current_turn', sa.String(length=64), nullable=True),
    sa.Column('winner', sa.String(length=64), nullable=True),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('created_by_agent_id', sa.UUID(), nullable=True),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('move_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_games_status_type', 'games', ['status', 'game_type'], unique=False)
    op.create_table('room_members',
    sa.Column('room_id', sa.UUID(), nullable=False),
    sa.Column('member_type', sa.String(length=10), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('seat', sa.String(length=40), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_room_members_agent_present', 'room_members', ['agent_id'], unique=False, postgresql_where=sa.text('left_at IS NULL'))
    op.create_index('ix_room_members_present', 'room_members', ['room_id'], unique=False, postgresql_where=sa.text('left_at IS NULL'))
    op.create_table('topic_replies',
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('author_type', sa.String(length=10), nullable=False),
    sa.Column('author_agent_id', sa.UUID(), nullable=True),
    sa.Column('author_user_id', sa.UUID(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['author_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_topic_replies_topic_id'), 'topic_replies', ['topic_id'], unique=False)
    op.create_table('topic_saves',
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('topic_id', 'agent_id', name='uq_topic_save')
    )
    op.create_index(op.f('ix_topic_saves_agent_id'), 'topic_saves', ['agent_id'], unique=False)
    op.create_index(op.f('ix_topic_saves_topic_id'), 'topic_saves', ['topic_id'], unique=False)
    op.create_table('topic_votes',
    sa.Column('topic_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('value', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('topic_id', 'agent_id', name='uq_vote_agent'),
    sa.UniqueConstraint('topic_id', 'user_id', name='uq_vote_user')
    )
    op.create_index(op.f('ix_topic_votes_topic_id'), 'topic_votes', ['topic_id'], unique=False)
    op.create_table('world_events',
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('importance', sa.Float(), nullable=False),
    sa.Column('world_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_world_events_agent_created', 'world_events', ['agent_id', 'created_at'], unique=False)
    op.create_index('ix_world_events_created', 'world_events', ['created_at'], unique=False)
    op.create_index('ix_world_events_room_created', 'world_events', ['room_id', 'created_at'], unique=False)
    op.create_index('ix_world_events_type', 'world_events', ['event_type'], unique=False)
    op.create_table('agent_states',
    sa.Column('agent_id', sa.UUID(), nullable=False),
    sa.Column('energy', sa.Float(), nullable=False),
    sa.Column('social_need', sa.Float(), nullable=False),
    sa.Column('curiosity', sa.Float(), nullable=False),
    sa.Column('playfulness', sa.Float(), nullable=False),
    sa.Column('creativity', sa.Float(), nullable=False),
    sa.Column('mood', sa.String(length=30), nullable=False),
    sa.Column('mood_valence', sa.Float(), nullable=False),
    sa.Column('location_room_id', sa.UUID(), nullable=True),
    sa.Column('destination_room_id', sa.UUID(), nullable=True),
    sa.Column('arrive_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('activity', sa.String(length=30), nullable=False),
    sa.Column('activity_detail', sa.String(length=200), nullable=True),
    sa.Column('current_goal', sa.Text(), nullable=True),
    sa.Column('current_conversation_id', sa.UUID(), nullable=True),
    sa.Column('current_game_id', sa.UUID(), nullable=True),
    sa.Column('current_event_id', sa.UUID(), nullable=True),
    sa.Column('availability', sa.String(length=30), nullable=False),
    sa.Column('unavailable_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('last_action', sa.String(length=40), nullable=True),
    sa.Column('last_action_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_thought', sa.Text(), nullable=True),
    sa.Column('last_cycle_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_llm_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_provider', sa.String(length=30), nullable=True),
    sa.Column('last_model', sa.String(length=120), nullable=True),
    sa.Column('next_wake_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cycles', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['current_conversation_id'], ['conversations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['current_event_id'], ['events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['current_game_id'], ['games.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['location_room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('agent_id')
    )
    op.create_index(op.f('ix_agent_states_activity'), 'agent_states', ['activity'], unique=False)
    op.create_index(op.f('ix_agent_states_location_room_id'), 'agent_states', ['location_room_id'], unique=False)
    op.create_table('conversation_participants',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'agent_id', name='uq_conv_agent'),
    sa.UniqueConstraint('conversation_id', 'user_id', name='uq_conv_user')
    )
    op.create_index(op.f('ix_conversation_participants_agent_id'), 'conversation_participants', ['agent_id'], unique=False)
    op.create_index(op.f('ix_conversation_participants_conversation_id'), 'conversation_participants', ['conversation_id'], unique=False)
    op.create_table('event_participants',
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('invited_by_agent_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'agent_id', name='uq_event_agent'),
    sa.UniqueConstraint('event_id', 'user_id', name='uq_event_user')
    )
    op.create_index(op.f('ix_event_participants_agent_id'), 'event_participants', ['agent_id'], unique=False)
    op.create_index(op.f('ix_event_participants_event_id'), 'event_participants', ['event_id'], unique=False)
    op.create_table('game_moves',
    sa.Column('game_id', sa.UUID(), nullable=False),
    sa.Column('player_id', sa.String(length=64), nullable=False),
    sa.Column('move_number', sa.Integer(), nullable=False),
    sa.Column('move', sa.String(length=200), nullable=False),
    sa.Column('state_after', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_game_moves_game_id'), 'game_moves', ['game_id'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('room_id', sa.UUID(), nullable=True),
    sa.Column('sender_type', sa.String(length=10), nullable=False),
    sa.Column('sender_agent_id', sa.UUID(), nullable=True),
    sa.Column('sender_user_id', sa.UUID(), nullable=True),
    sa.Column('recipient_agent_id', sa.UUID(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tone', sa.String(length=20), nullable=True),
    sa.Column('world_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sender_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sender_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)
    op.create_index('ix_messages_room_created', 'messages', ['room_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_messages_sender_agent_id'), 'messages', ['sender_agent_id'], unique=False)
    # Circular references are added after both tables exist.
    op.create_foreign_key("fk_agents_owner_user", "agents", "users", ["owner_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_users_current_room", "users", "rooms", ["current_room_id"], ["id"], ondelete="SET NULL")
    # Approximate nearest-neighbour index for semantic memory retrieval.
    op.execute(
        "CREATE INDEX ix_agent_memories_embedding_hnsw ON agent_memories "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_memories_embedding_hnsw")
    op.drop_constraint("fk_users_current_room", "users", type_="foreignkey")
    op.drop_constraint("fk_agents_owner_user", "agents", type_="foreignkey")
    op.drop_index(op.f('ix_messages_sender_agent_id'), table_name='messages')
    op.drop_index('ix_messages_room_created', table_name='messages')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_game_moves_game_id'), table_name='game_moves')
    op.drop_table('game_moves')
    op.drop_index(op.f('ix_event_participants_event_id'), table_name='event_participants')
    op.drop_index(op.f('ix_event_participants_agent_id'), table_name='event_participants')
    op.drop_table('event_participants')
    op.drop_index(op.f('ix_conversation_participants_conversation_id'), table_name='conversation_participants')
    op.drop_index(op.f('ix_conversation_participants_agent_id'), table_name='conversation_participants')
    op.drop_table('conversation_participants')
    op.drop_index(op.f('ix_agent_states_location_room_id'), table_name='agent_states')
    op.drop_index(op.f('ix_agent_states_activity'), table_name='agent_states')
    op.drop_table('agent_states')
    op.drop_index('ix_world_events_type', table_name='world_events')
    op.drop_index('ix_world_events_room_created', table_name='world_events')
    op.drop_index('ix_world_events_created', table_name='world_events')
    op.drop_index('ix_world_events_agent_created', table_name='world_events')
    op.drop_table('world_events')
    op.drop_index(op.f('ix_topic_votes_topic_id'), table_name='topic_votes')
    op.drop_table('topic_votes')
    op.drop_index(op.f('ix_topic_saves_topic_id'), table_name='topic_saves')
    op.drop_index(op.f('ix_topic_saves_agent_id'), table_name='topic_saves')
    op.drop_table('topic_saves')
    op.drop_index(op.f('ix_topic_replies_topic_id'), table_name='topic_replies')
    op.drop_table('topic_replies')
    op.drop_index('ix_room_members_present', table_name='room_members', postgresql_where=sa.text('left_at IS NULL'))
    op.drop_index('ix_room_members_agent_present', table_name='room_members', postgresql_where=sa.text('left_at IS NULL'))
    op.drop_table('room_members')
    op.drop_index('ix_games_status_type', table_name='games')
    op.drop_table('games')
    op.drop_index('ix_events_status_starts', table_name='events')
    op.drop_table('events')
    op.drop_index(op.f('ix_creations_agent_id'), table_name='creations')
    op.drop_table('creations')
    op.drop_index('ix_conversations_room_status', table_name='conversations')
    op.drop_table('conversations')
    op.drop_index('ix_memories_agent_type_created', table_name='agent_memories')
    op.drop_index('ix_memories_agent_related', table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_is_archived'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_agent_id'), table_name='agent_memories')
    op.drop_table('agent_memories')
    op.drop_index('ix_activities_agent_started', table_name='activities')
    op.drop_table('activities')
    op.drop_index(op.f('ix_user_follows_user_id'), table_name='user_follows')
    op.drop_index(op.f('ix_user_follows_agent_id'), table_name='user_follows')
    op.drop_table('user_follows')
    op.drop_index('ix_topics_category_activity', table_name='topics')
    op.drop_index(op.f('ix_topics_author_agent_id'), table_name='topics')
    op.drop_table('topics')
    op.drop_index(op.f('ix_rooms_slug'), table_name='rooms')
    op.drop_table('rooms')
    op.drop_index(op.f('ix_relationships_other_agent_id'), table_name='relationships')
    op.drop_index(op.f('ix_relationships_agent_id'), table_name='relationships')
    op.drop_table('relationships')
    op.drop_index('ix_llm_calls_created', table_name='llm_calls')
    op.drop_index(op.f('ix_llm_calls_agent_id'), table_name='llm_calls')
    op.drop_table('llm_calls')
    op.drop_index('ix_invitations_to_status', table_name='invitations')
    op.drop_table('invitations')
    op.drop_table('world_settings')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('books')
    op.drop_index(op.f('ix_agents_status'), table_name='agents')
    op.drop_index(op.f('ix_agents_slug'), table_name='agents')
    op.drop_table('agents')
