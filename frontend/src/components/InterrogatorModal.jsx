import { useState } from 'react';
import { Modal, TextLink } from './primitives';

export default function InterrogatorModal({
  isOpen,
  question,
  questionNumber,
  minQuestions,
  maxQuestions,
  isSubmitting,
  onSubmitAnswer,
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
      <div className="pt-1">
        <TextLink as="button" variant="muted" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </TextLink>
      </div>
    </Modal>
  );
}
