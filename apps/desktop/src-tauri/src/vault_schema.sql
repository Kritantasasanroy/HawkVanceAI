-- The local vault.
--
-- Every table here lives inside a SQLCipher-encrypted file, and the columns holding anything a
-- person would recognise as their own content are additionally sealed per value. Columns that are
-- only ever used to look a row up (ids, timestamps, counts) are left in the clear, because an
-- index over sealed values cannot be searched and would buy nothing.

create table if not exists workspaces (
  id            text primary key,
  name          text not null,
  description   text not null default '',
  created_at    text not null,
  updated_at    text not null
);

create table if not exists documents (
  id              text primary key,
  -- Null means Global memory: a file not tied to any one project.
  workspace_id    text references workspaces (id) on delete cascade,
  filename        text not null,
  sha256          text not null,
  size_bytes      integer not null,
  character_count integer not null,
  used_ocr        integer not null default 0,
  -- Sealed. This is the sanitised text, never the original, but it is still the person's document.
  sanitised_text  text not null,
  created_at      text not null
);

-- Partial, because SQLite treats every null as distinct: without the `where` clause the same file
-- could be added to Global memory over and over without the unique constraint ever noticing.
create unique index if not exists documents_workspace_sha
  on documents (workspace_id, sha256) where workspace_id is not null;
create unique index if not exists documents_global_sha
  on documents (sha256) where workspace_id is null;

-- What turns [ORG_001] back into the real name.
--
-- This table is the reason the product works, and the most sensitive thing in the file. It is
-- written only by the Rust side, has no read path that reaches the web view, and every original
-- is sealed individually.
create table if not exists redaction_map_entries (
  id            integer primary key autoincrement,
  document_id   text not null references documents (id) on delete cascade,
  workspace_id  text,
  placeholder   text not null,
  -- Sealed.
  original      text not null,
  category      text not null,
  created_at    text not null
);

create index if not exists redaction_entries_by_document on redaction_map_entries (document_id);
create index if not exists redaction_entries_by_workspace on redaction_map_entries (workspace_id);

create table if not exists conversations (
  id           text primary key,
  workspace_id text references workspaces (id) on delete cascade,
  title        text not null default '',
  started_at   text not null
);

create table if not exists conversation_turns (
  id              text primary key,
  conversation_id text not null references conversations (id) on delete cascade,
  role            text not null,
  -- Sealed.
  content         text not null,
  model           text,
  occurred_at     text not null
);

create index if not exists turns_by_conversation on conversation_turns (conversation_id, occurred_at);

-- Words the person marked to hide. Scope is either a workspace id or the literal 'global'.
create table if not exists protected_terms (
  scope      text not null,
  term       text not null,
  created_at text not null,
  primary key (scope, term)
);

-- Small named values the app remembers between runs: the chosen model, whether the thread rail is
-- open. Namespaced by the caller, and deliberately not a general key-value store for content.
create table if not exists settings (
  key        text primary key,
  value      text not null,
  updated_at text not null
);
