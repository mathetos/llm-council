import { useState } from 'react';
import { Modal, TextLink } from './primitives';

function CoverageIndicator({ coverage }) {
  if (!coverage?.fields) return null;
  const entries = Object.entries(coverage.fields);
  if (entries.length === 0) return null;

  const statusIcon = { covered: '✅', partial: '⚠️', missing: '❌', unknown: '❓' };
  const ratio = coverage.coverage_ratio != null ? Math.round(coverage.coverage_ratio * 100) : null;

  return (
    <div className="mt-2 rounded-md border border-border bg-muted/20 p-2 text-xs">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-medium text-muted-foreground">Context Coverage</span>
        {ratio != null && (
          <span className="font-mono text-muted-foreground">{ratio}%</span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {entries.map(([field, status]) => (
          <span key={field}>
            {statusIcon[status] || '❓'} {field}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function InterrogatorModal({
  isOpen,
  question,
  questionNumber,
  minQuestions,
  maxQuestions,
  isSubmitting,
  awaitingConfirmation,
  confirmationSummary,
  coverage,
  onSubmitAnswer,
  onConfirm,
  onDefer,
  onCancel,
}) {
  const [answer, setAnswer] = useState('');

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;
    onSubmitAnswer(answer.trim());
  };

  if (awaitingConfirmation) {
    return (
      <Modal
        open={isOpen}
        onClose={onCancel}
        title="Confirm Before Council Deliberation"
        description="The interrogator has identified gaps in context. Review the summary below."
        primaryAction={isSubmitting ? 'Confirming...' : 'Proceed to Council'}
        secondaryAction="I Have More Context"
        onPrimaryAction={() => !isSubmitting && onConfirm(true)}
        onSecondaryAction={() => !isSubmitting && onConfirm(false)}
        isLoading={isSubmitting}
      >
        <div className="space-y-3">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-foreground dark:border-amber-700 dark:bg-amber-950/30">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
              Interrogator Summary
            </p>
            <p className="whitespace-pre-wrap">{confirmationSummary}</p>
          </div>
          <CoverageIndicator coverage={coverage} />
          <p className="text-xs text-muted-foreground">
            You can proceed with known gaps (the council will state assumptions), or provide more context.
          </p>
        </div>
        <div className="pt-1">
          <TextLink as="button" variant="muted" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </TextLink>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open={isOpen}
      onClose={onCancel}
      title="Interrogator Clarifying Questions"
      description={`Question ${questionNumber} of ${maxQuestions} (minimum required: ${minQuestions})`}
      primaryAction={isSubmitting ? 'Submitting...' : 'Submit Answer'}
      secondaryAction="Defer This Aspect to Council"
      onPrimaryAction={() => {
        if (answer.trim() && !isSubmitting) {
          onSubmitAnswer(answer.trim());
        }
      }}
      onSecondaryAction={onDefer}
      isLoading={isSubmitting}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <p className="rounded-md border border-border bg-muted/30 p-3 text-sm text-foreground">
          {question}
        </p>
        <textarea
          className="min-h-28 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={4}
          placeholder="Your answer..."
          disabled={isSubmitting}
        />
      </form>
      <CoverageIndicator coverage={coverage} />
      <div className="pt-1">
        <TextLink as="button" variant="muted" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </TextLink>
      </div>
    </Modal>
  );
}
