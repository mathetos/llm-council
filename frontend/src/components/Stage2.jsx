import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { TabBar } from './primitives';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  // Replace each "Response X" with the actual model name
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h3 className="text-base font-semibold text-foreground">Stage 2: Peer Rankings</h3>

      <h4 className="text-sm font-semibold text-foreground">Raw Evaluations</h4>
      <p className="text-xs text-muted-foreground">
        Each model evaluated all responses (anonymized as Response A, B, C, etc.) and provided rankings.
        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
      </p>

      <TabBar
        value={String(activeTab)}
        onChange={(value) => setActiveTab(Number(value))}
        options={rankings.map((rank, index) => ({
          value: String(index),
          label: rank.model.split('/')[1] || rank.model,
        }))}
      />

      <div className="space-y-2 rounded-md border border-border bg-background p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {rankings[activeTab].model}
        </div>
        <div className="markdown-content text-sm text-foreground">
          <ReactMarkdown>
            {deAnonymizeText(rankings[activeTab].ranking, labelToModel)}
          </ReactMarkdown>
        </div>

        {rankings[activeTab].parsed_ranking &&
         rankings[activeTab].parsed_ranking.length > 0 && (
          <div className="rounded-md border border-border bg-card p-3">
            <strong className="text-sm text-foreground">Extracted Ranking:</strong>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-foreground">
              {rankings[activeTab].parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labelToModel && labelToModel[label]
                    ? labelToModel[label].split('/')[1] || labelToModel[label]
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="space-y-2 rounded-md border border-border bg-background p-3">
          <h4 className="text-sm font-semibold text-foreground">Aggregate Rankings (Street Cred)</h4>
          <p className="text-xs text-muted-foreground">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="space-y-2">
            {aggregateRankings.map((agg, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
                <span className="font-semibold text-foreground">#{index + 1}</span>
                <span className="font-medium text-foreground">
                  {agg.model.split('/')[1] || agg.model}
                </span>
                <span className="text-muted-foreground">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="text-xs text-muted-foreground">
                  ({agg.rankings_count} votes)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
