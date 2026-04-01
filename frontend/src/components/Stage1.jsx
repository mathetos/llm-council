import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { TabBar } from './primitives';

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h3 className="text-base font-semibold text-foreground">Stage 1: Individual Responses</h3>

      <TabBar
        value={String(activeTab)}
        onChange={(value) => setActiveTab(Number(value))}
        options={responses.map((resp, index) => ({
          value: String(index),
          label: resp.model.split('/')[1] || resp.model,
        }))}
      />

      <div className="space-y-2 rounded-md border border-border bg-background p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {responses[activeTab].model}
        </div>
        <div className="markdown-content text-sm text-foreground">
          <ReactMarkdown>{responses[activeTab].response}</ReactMarkdown>
        </div>
      </div>
    </section>
  );
}
