import { z } from "zod";

export const SessionCreateRequestSchema = z.object({
  run_id: z.string(),
  headless: z.boolean().default(true),
  viewport: z
    .object({
      width: z.number().default(1280),
      height: z.number().default(800),
    })
    .default({ width: 1280, height: 800 }),
  allowed_hosts: z.array(z.string()).default([]),
});

export type SessionCreateRequest = z.infer<typeof SessionCreateRequestSchema>;

export const UiActionEnum = z.enum([
  "navigate",
  "fill_by_label",
  "click_by_role",
  "assert_visible",
  "assert_text",
  "assert_url",
  "screenshot",
  "ai_act",
  "ai_assert",
  "ai_wait_for",
  "ai_query",
]);

export type UiAction = z.infer<typeof UiActionEnum>;

export const UiCommandSchema = z.object({
  protocol_version: z.string().default("1.0"),
  run_id: z.string(),
  test_id: z.string(),
  step_index: z.number(),
  action: UiActionEnum,
  params: z.record(z.any()).default({}),
  candidate_locators: z.array(z.record(z.any())).optional(),
  timeout_ms: z.number().default(15000),
});

export type UiCommand = z.infer<typeof UiCommandSchema>;

export const UiStepResultSchema = z.object({
  protocol_version: z.string().default("1.0"),
  run_id: z.string(),
  test_id: z.string(),
  step_index: z.number(),
  outcome: z.enum(["PASSED", "FAILED", "ERROR", "TIMED_OUT"]),
  engine: z.string().default("midscene"),
  duration_ms: z.number(),
  observed: z.string(),
  error_code: z.string().nullable().optional(),
  evidence_ids: z.array(z.string()).default([]),
  details: z.record(z.any()).default({}),
});

export type UiStepResult = z.infer<typeof UiStepResultSchema>;
