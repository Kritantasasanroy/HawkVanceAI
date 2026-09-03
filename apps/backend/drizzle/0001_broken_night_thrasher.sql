ALTER TABLE "hawkvance"."accounts" ADD COLUMN "occupation" text;--> statement-breakpoint
ALTER TABLE "hawkvance"."accounts" ADD COLUMN "onboarded_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "hawkvance"."plan_limits" ADD COLUMN "monthly_credits" integer DEFAULT 500 NOT NULL;--> statement-breakpoint
ALTER TABLE "hawkvance"."usage_records" ADD COLUMN "credits_spent" integer DEFAULT 0 NOT NULL;