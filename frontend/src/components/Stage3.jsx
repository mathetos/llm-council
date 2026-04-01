import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Button } from './primitives';

export default function Stage3({
  finalResponse,
  onSaveVerdict,
  existingVerdict,
  onRerun,
  rerunDisabled = false,
}) {
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [savedFilename, setSavedFilename] = useState(existingVerdict?.filename || '');

  useEffect(() => {
    setSavedFilename(existingVerdict?.filename || '');
  }, [existingVerdict?.filename]);

  if (!finalResponse) {
    return null;
  }

  const handleSave = async () => {
    if (!onSaveVerdict || isSaving || savedFilename) return;

    setIsSaving(true);
    setSaveMessage('');
    try {
      const result = await onSaveVerdict();
      if (result?.filename) {
        setSavedFilename(result.filename);
        setSaveMessage(`Verdict already saved locally as: ${result.filename}`);
      } else {
        setSaveMessage('Saved verdict markdown');
      }
    } catch (error) {
      setSaveMessage('Failed to save markdown');
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="space-y-3 rounded-lg border border-accent/40 bg-accent/15 p-4">
      <h3 className="text-base font-semibold text-foreground">Stage 3: Final Council Answer</h3>
      <div className="space-y-2 rounded-md border border-border bg-card p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Chairman: {finalResponse.model.split('/')[1] || finalResponse.model}
        </div>
        <div className="markdown-content text-sm text-foreground">
          <ReactMarkdown>{finalResponse.response}</ReactMarkdown>
        </div>
        <div className="flex min-w-0 items-center gap-3">
          <Button
            type="button"
            size="sm"
            className="shrink-0 min-w-[190px]"
            onClick={handleSave}
            isLoading={isSaving}
            disabled={Boolean(savedFilename)}
          >
            {isSaving ? 'Saving...' : 'Save Verdict as Markdown'}
          </Button>
          {onRerun ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="shrink-0 min-w-[80px]"
              onClick={onRerun}
              disabled={rerunDisabled}
            >
              Re-run
            </Button>
          ) : null}
          {(savedFilename || saveMessage) && (
            <span
              className="min-w-0 flex-1 truncate text-sm text-muted-foreground"
              title={
                savedFilename
                  ? `Verdict already saved locally as: ${savedFilename}`
                  : saveMessage
              }
            >
              {savedFilename
                ? `Verdict already saved locally as: ${savedFilename}`
                : saveMessage}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
