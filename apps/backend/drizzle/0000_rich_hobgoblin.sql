CREATE SCHEMA "hawkvance";
--> statement-breakpoint
CREATE TABLE "hawkvance"."accounts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"neon_user_id" text NOT NULL,
	"email" text NOT NULL,
	"email_domain" text NOT NULL,
	"display_name" text NOT NULL,
	"status" text DEFAULT 'active' NOT NULL,
	"role" text DEFAULT 'member' NOT NULL,
	"plan" text DEFAULT 'beta' NOT NULL,
	"suspended_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hawkvance"."activity_events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL,
	"kind" text NOT NULL,
	"detail" jsonb NOT NULL,
	"request_ip" text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hawkvance"."admin_audit_entries" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"actor_account_id" uuid NOT NULL,
	"subject_account_id" uuid,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL,
	"action" text NOT NULL,
	"previous_value" jsonb NOT NULL,
	"next_value" jsonb NOT NULL,
	"request_ip" text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hawkvance"."devices" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"name" text NOT NULL,
	"platform" text NOT NULL,
	"app_version" text NOT NULL,
	"first_seen_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hawkvance"."plan_limits" (
	"tier" text PRIMARY KEY NOT NULL,
	"daily_requests" integer NOT NULL,
	"monthly_requests" integer NOT NULL,
	"monthly_tokens" bigint NOT NULL,
	"storage_bytes" bigint NOT NULL,
	"max_workspaces" integer NOT NULL,
	"memory_retention_days" integer NOT NULL,
	"byok_allowed" boolean NOT NULL,
	"allowed_model_tiers" jsonb NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "hawkvance"."usage_records" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"workspace_id" uuid,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL,
	"provider" text NOT NULL,
	"model" text NOT NULL,
	"input_tokens" integer NOT NULL,
	"output_tokens" integer NOT NULL,
	"estimated_cost_micros" bigint NOT NULL,
	"latency_ms" integer NOT NULL,
	"outcome" text NOT NULL
);
--> statement-breakpoint
ALTER TABLE "hawkvance"."activity_events" ADD CONSTRAINT "activity_events_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "hawkvance"."accounts"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "hawkvance"."admin_audit_entries" ADD CONSTRAINT "admin_audit_entries_actor_account_id_accounts_id_fk" FOREIGN KEY ("actor_account_id") REFERENCES "hawkvance"."accounts"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "hawkvance"."admin_audit_entries" ADD CONSTRAINT "admin_audit_entries_subject_account_id_accounts_id_fk" FOREIGN KEY ("subject_account_id") REFERENCES "hawkvance"."accounts"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "hawkvance"."devices" ADD CONSTRAINT "devices_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "hawkvance"."accounts"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "hawkvance"."usage_records" ADD CONSTRAINT "usage_records_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "hawkvance"."accounts"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "accounts_neon_user_unique" ON "hawkvance"."accounts" USING btree ("neon_user_id");--> statement-breakpoint
CREATE UNIQUE INDEX "accounts_email_unique" ON "hawkvance"."accounts" USING btree ("email");--> statement-breakpoint
CREATE INDEX "accounts_status_idx" ON "hawkvance"."accounts" USING btree ("status");--> statement-breakpoint
CREATE INDEX "activity_events_account_time_idx" ON "hawkvance"."activity_events" USING btree ("account_id","occurred_at");--> statement-breakpoint
CREATE INDEX "admin_audit_time_idx" ON "hawkvance"."admin_audit_entries" USING btree ("occurred_at");--> statement-breakpoint
CREATE UNIQUE INDEX "devices_account_name_unique" ON "hawkvance"."devices" USING btree ("account_id","name","platform");--> statement-breakpoint
CREATE INDEX "devices_account_idx" ON "hawkvance"."devices" USING btree ("account_id");--> statement-breakpoint
CREATE INDEX "usage_records_account_time_idx" ON "hawkvance"."usage_records" USING btree ("account_id","occurred_at");--> statement-breakpoint
CREATE INDEX "usage_records_model_idx" ON "hawkvance"."usage_records" USING btree ("model","occurred_at");