export type Step = {
  tool: string;
  args: Record<string, unknown>;
  specialist: string;
  depends_on: number[];
};
export type ToolResult = {
  step: number;
  tool: string;
  ok: boolean;
  result?: unknown;
  error?: string;
};
export type Run = {
  id: string;
  user_request: string;
  conversation_id: string;
  plan: Step[];
  tool_results: ToolResult[];
  status: string;
  cursor: number;
  final_response: string;
  created_at: string;
  provider: string;
  errors: { message: string }[];
};
export type Resource = {
  id: string;
  status: string;
  building?: string;
  floor?: number;
  description?: string;
  category?: string;
  priority?: string;
  start_time?: string;
  end_time?: string;
  resource?: { name: string; kind: string; building: string };
};
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    credentials: "same-origin",
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.error === "string"
        ? data.error
        : typeof data.detail === "string"
          ? data.detail
          : "Something went wrong. Please try again.",
    );
  return data;
}
