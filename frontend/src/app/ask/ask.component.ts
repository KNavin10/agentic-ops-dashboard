import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize, timeout } from 'rxjs';
import Highcharts from 'highcharts';

import {
  AgentApiService,
  AgentMetrics,
  ApprovalRequest,
  AskResponse,
  DataRow,
  StreamEvent,
  TraceStep,
} from '../agent-api.service';

@Component({
  selector: 'app-ask',
  imports: [CommonModule, FormsModule],
  templateUrl: './ask.component.html',
  styleUrl: './ask.component.css',
})
export class AskComponent implements AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') chartContainer?: ElementRef<HTMLDivElement>;

  question = '';
  answer = '';
  trace: TraceStep[] = [];
  rows: DataRow[] = [];
  approval: ApprovalRequest | null = null;
  statusMessage = 'Ready';
  errorMessage = '';
  loading = false;
  metrics: AgentMetrics = {
    runs_today: 0,
    success_rate: 0,
    average_steps: 0,
    spend_today_usd: 0,
  };
  latestRequestId = '';

  private chart?: Highcharts.Chart;
  private readonly api = inject(AgentApiService);
  private readonly changeDetector = inject(ChangeDetectorRef);

  ngAfterViewInit(): void {
    this.renderChart();
    this.refreshMetrics();
  }

  submit(): void {
    const trimmedQuestion = this.question.trim();

    if (!trimmedQuestion || this.loading) {
      this.statusMessage = 'Enter a question first.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.statusMessage = 'Asking the agent...';
    this.clearResults();

    this.api.ask(trimmedQuestion).pipe(
      timeout(30000),
      finalize(() => {
        this.loading = false;
        this.refreshMetrics();
        this.changeDetector.detectChanges();
      }),
    ).subscribe({
      next: (response) => this.showResponse(response),
      error: (error: unknown) => {
        const requestError = error as {
          name?: string;
          error?: { detail?: string };
        };
        this.errorMessage = requestError.name === 'TimeoutError'
          ? 'The FastAPI request took longer than 30 seconds.'
          : requestError.error?.detail || 'The FastAPI request failed.';
        this.statusMessage = 'Request failed';
        this.changeDetector.detectChanges();
      },
    });
  }

  submitStream(): void {
    const trimmedQuestion = this.question.trim();

    if (!trimmedQuestion || this.loading) {
      this.statusMessage = 'Enter a question first.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.statusMessage = 'Opening stream...';
    this.clearResults();

    this.api.askStream(trimmedQuestion, (event) => this.showStreamEvent(event))
      .then(() => {
        if (!this.approval) {
          this.statusMessage = 'ok';
        }
      })
      .catch((error: unknown) => {
        this.errorMessage = error instanceof Error ? error.message : 'The streaming request failed.';
        this.statusMessage = 'Request failed';
      })
      .finally(() => {
        this.loading = false;
        this.refreshMetrics();
        this.changeDetector.detectChanges();
      });
  }

  declineApproval(): void {
    if (!this.approval) {
      return;
    }
    const approvalId = this.approval.approval_id;
    this.approval = null;
    this.api.decideApproval(approvalId, 'decline').subscribe({
      next: (response) => this.showResponse(response),
      error: () => this.statusMessage = 'Approval request could not be declined.',
    });
  }

  approveRequest(): void {
    if (!this.approval) {
      return;
    }
    const approvalId = this.approval.approval_id;
    this.approval = null;
    this.statusMessage = 'Submitting approval...';
    this.api.decideApproval(approvalId, 'approve').subscribe({
      next: (response) => this.showResponse(response),
      error: () => this.statusMessage = 'Approval request could not be completed.',
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private showResponse(response: AskResponse): void {
    this.latestRequestId = response.request_id || '';
    this.answer = response.answer || '';
    this.trace = response.trace || [];
    this.rows = response.rows || [];
    this.approval = response.status === 'awaiting_approval'
      ? response.approval || null
      : null;
    this.statusMessage = response.status;
    this.renderChart();
    this.changeDetector.detectChanges();
  }

  private showStreamEvent(event: StreamEvent): void {
    if (event.type === 'text') {
      this.answer += event.text;
    } else if (event.type === 'tool') {
      this.trace = [
        ...this.trace,
        { step: this.trace.length, tool: event.tool, status: `${event.row_count} rows` },
      ];
    } else if (event.type === 'rows') {
      this.rows = event.rows;
      this.renderChart();
    } else if (event.type === 'approval') {
      this.approval = {
        approval_id: event.approval_id,
        tool: event.tool,
        arguments: event.arguments,
      };
      this.statusMessage = 'awaiting_approval';
    } else if (event.type === 'done') {
      this.latestRequestId = event.request_id || '';
    }

    this.changeDetector.detectChanges();
  }

  private refreshMetrics(): void {
    this.api.getMetrics().subscribe({
      next: (metrics) => {
        this.metrics = metrics;
        this.changeDetector.detectChanges();
      },
    });
  }

  private clearResults(): void {
    this.answer = '';
    this.latestRequestId = '';
    this.trace = [];
    this.rows = [];
    this.approval = null;
    this.chart?.destroy();
    this.chart = undefined;
  }

  private renderChart(): void {
    if (!this.chartContainer) {
      return;
    }

    this.chart?.destroy();

    if (!this.rows.length) {
      return;
    }

    const categories = this.rows.map((row, index) =>
      String(row['id'] ?? row['month'] ?? `Row ${index + 1}`),
    );
    const values = this.rows.map((row) =>
      Number(row['days_late'] ?? row['total_submissions'] ?? 0),
    );

    this.chart = Highcharts.chart(this.chartContainer.nativeElement, {
      title: { text: 'Returned rows' },
      xAxis: { categories },
      yAxis: { title: { text: 'Value' } },
      series: [{
        type: 'column',
        name: 'Days late / total submissions',
        data: values,
      }],
      credits: { enabled: false },
    });
  }
}
