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

  private chart?: Highcharts.Chart;
  private readonly api = inject(AgentApiService);
  private readonly changeDetector = inject(ChangeDetectorRef);

  ngAfterViewInit(): void {
    this.renderChart();
  }

  submit(approveSensitive = false): void {
    const trimmedQuestion = this.question.trim();

    if (!trimmedQuestion || this.loading) {
      this.statusMessage = 'Enter a question first.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.statusMessage = approveSensitive ? 'Submitting approval...' : 'Asking the agent...';
    this.clearResults();

    this.api.ask(trimmedQuestion, approveSensitive).pipe(
      timeout(30000),
      finalize(() => {
        this.loading = false;
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

    this.api.askStream(trimmedQuestion, false, (event) => this.showStreamEvent(event))
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
        this.changeDetector.detectChanges();
      });
  }

  declineApproval(): void {
    this.approval = null;
    this.statusMessage = 'Approval declined. No write request was sent.';
  }

  approveRequest(): void {
    this.approval = null;
    this.submit(true);
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  private showResponse(response: AskResponse): void {
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
      this.approval = { tool: event.tool, arguments: event.arguments };
      this.statusMessage = 'awaiting_approval';
    }

    this.changeDetector.detectChanges();
  }

  private clearResults(): void {
    this.answer = '';
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
