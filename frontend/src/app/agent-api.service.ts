import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TraceStep {
  step: number;
  tool: string;
  status: string;
}

export interface DataRow {
  [key: string]: string | number | null;
}

export interface ApprovalRequest {
  tool: string;
  arguments: Record<string, unknown>;
}

export interface AskResponse {
  status: string;
  answer?: string;
  trace: TraceStep[];
  rows: DataRow[];
  approval?: ApprovalRequest | null;
  tokens?: number;
  request_id?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  latency_ms?: number;
  cached?: boolean;
}

export interface AgentMetrics {
  runs_today: number;
  success_rate: number;
  average_steps: number;
  spend_today_usd: number;
}

export type StreamEvent =
  | { type: 'text'; text: string }
  | { type: 'tool'; tool: string; row_count: number }
  | { type: 'rows'; rows: DataRow[] }
  | { type: 'approval'; tool: string; arguments: Record<string, unknown> }
  | { type: 'done'; request_id?: string };

@Injectable({ providedIn: 'root' })
export class AgentApiService {
  private readonly http = inject(HttpClient);

  ask(question: string, approveSensitive = false): Observable<AskResponse> {
    return this.http.post<AskResponse>('/api/ask', {
      question,
      approve_sensitive: approveSensitive,
    });
  }

  getMetrics(): Observable<AgentMetrics> {
    return this.http.get<AgentMetrics>('/metrics');
  }

  async askStream(
    question: string,
    approveSensitive: boolean,
    onEvent: (event: StreamEvent) => void,
  ): Promise<void> {
    const token = localStorage.getItem('agent_api_token');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/api/ask/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        question,
        approve_sensitive: approveSensitive,
      }),
    });

    if (!response.ok) {
      throw new Error(`The streaming request failed (${response.status}).`);
    }

    if (!response.body) {
      throw new Error('The browser did not provide a readable response stream.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.trim()) {
          onEvent(JSON.parse(line) as StreamEvent);
        }
      }

      if (done) {
        break;
      }
    }

    if (buffer.trim()) {
      onEvent(JSON.parse(buffer) as StreamEvent);
    }
  }
}
