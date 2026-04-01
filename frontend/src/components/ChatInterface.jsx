import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import InterrogatorModal from './InterrogatorModal';
import { Button, Modal, Tooltip } from './primitives';

function GuardrailStatusPill({ guardrailStatus }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const status = guardrailStatus?.status || 'unknown';
  const violations = guardrailStatus?.violations || [];

  const toneClass =
    status === 'pass'
      ? 'border-accent bg-accent/20 text-foreground'
      : status === 'degraded'
      ? 'border-primary/30 bg-primary/10 text-foreground'
      : 'border-destructive/30 bg-destructive/10 text-foreground';

  const statusLine = `Guardrails: ${status}${
    violations.length ? ` (${violations.length} issue${violations.length === 1 ? '' : 's'})` : ''
  }`;

  const tooltipText =
    status === 'degraded'
      ? [
          'Degraded means one or more quality guardrails were not fully met.',
          '',
          'Why:',
          ...(violations.length ? violations.map((item) => `- ${item}`) : ['- No detailed violations returned']),
          '',
          'What you can do:',
          '- Add more context in profile + packet inputs.',
          '- Keep role assignments diverse (avoid role/model over-collapsing).',
          '- If needed, adjust guardrail thresholds or enforcement mode.',
        ].join('\n')
      : status === 'fail'
      ? [
          'Fail means strict guardrail enforcement blocked the final quality gate.',
          '',
          'Why:',
          ...(violations.length ? violations.map((item) => `- ${item}`) : ['- No detailed violations returned']),
          '',
          'What you can do:',
          '- Fix the listed violations and retry.',
          '- Relax strict mode only if appropriate for your use case.',
        ].join('\n')
      : 'Guardrails passed. No intervention needed.';

  return (
    <span
      className={`relative inline-flex rounded-full border px-2.5 py-1 text-xs ${toneClass}`}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onFocus={() => setShowTooltip(true)}
      onBlur={() => setShowTooltip(false)}
      tabIndex={0}
      aria-label={statusLine}
    >
      {statusLine}
      <Tooltip
        text={tooltipText}
        show={showTooltip}
        position="right"
        className="w-80 max-w-[80vw] whitespace-pre-line text-left leading-relaxed"
      />
    </span>
  );
}

export default function ChatInterface({
  conversation,
  onSendMessage,
  onStopCouncil,
  isLoading,
  onSaveVerdictAsMarkdown,
  interrogationState,
  onSubmitInterrogationAnswer,
  onDeferInterrogation,
  onCancelInterrogation,
  selectedProfileId,
  selectedPacketId,
  selectedModelPairingId,
  selectedModelPairingLabel,
  selectedPairingModels,
  modelPairings,
  currentRoleAssignments,
}) {
  const [input, setInput] = useState('');
  const [rerunChoice, setRerunChoice] = useState({
    open: false,
    prompt: '',
    sourceConfig: null,
    currentConfig: null,
  });
  const [rerunConfirm, setRerunConfirm] = useState({
    open: false,
    prompt: '',
    config: null,
  });
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const getPromptForAssistantMessage = (assistantMessageIndex) => {
    if (!conversation?.messages?.length) return '';
    for (let i = assistantMessageIndex - 1; i >= 0; i -= 1) {
      const candidate = conversation.messages[i];
      if (candidate?.role === 'user' && candidate?.content) {
        return candidate.content;
      }
    }
    return '';
  };

  const roleAssignmentsListToMap = (items = []) => {
    const map = {};
    items.forEach((item) => {
      if (item?.role_id) {
        map[item.role_id] = item.model || '';
      }
    });
    return map;
  };

  const normalizeConfig = (config) => ({
    profile_id: config?.profile_id || '',
    packet_id: config?.packet_id || '',
    model_pairing_id: config?.model_pairing_id || '',
    role_assignments: config?.role_assignments || {},
    models: config?.models || [],
  });

  const getPairingLabel = (pairingId) => {
    if (!pairingId) return '';
    const pairing = (modelPairings || []).find((item) => item.id === pairingId);
    return pairing?.label || pairingId;
  };

  const getModelsFromRoleAssignments = (roleAssignments = {}) =>
    [...new Set(Object.values(roleAssignments || {}).filter(Boolean))];

  const compactModels = (models = []) =>
    [...new Set((models || []).filter(Boolean))];

  const getConfigModels = (config) => {
    const roleAssigned = getModelsFromRoleAssignments(config?.role_assignments || {});
    if (roleAssigned.length) return roleAssigned;
    return compactModels(config?.models || []);
  };

  const renderConfigSummary = (title, config, fallbackPairingLabel = '') => {
    const profile = config?.profile_id || 'unknown';
    const packet = config?.packet_id || 'default';
    const pairingLabel = getPairingLabel(config?.model_pairing_id) || fallbackPairingLabel || 'unknown';
    const models = getConfigModels(config);
    return (
      <div className="space-y-1 rounded-md border border-border bg-muted/30 px-3 py-2">
        <p>
          <span className="font-semibold text-foreground">{title}</span>
          {`: ${profile} / ${packet}`}
        </p>
        <p>
          <span className="font-semibold text-foreground">Model pairing:</span> {pairingLabel}
        </p>
        <p className="break-words">
          <span className="font-semibold text-foreground">Models:</span>{' '}
          {models.length ? models.join(', ') : 'unknown'}
        </p>
      </div>
    );
  };

  const areRoleAssignmentsEqual = (left = {}, right = {}) => {
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    if (leftKeys.length !== rightKeys.length) return false;
    return leftKeys.every((key) => (left[key] || '') === (right[key] || ''));
  };

  const areConfigsEqual = (leftInput, rightInput) => {
    const left = normalizeConfig(leftInput);
    const right = normalizeConfig(rightInput);
    if (left.profile_id !== right.profile_id) return false;
    if (left.packet_id !== right.packet_id) return false;
    if (left.model_pairing_id !== right.model_pairing_id) return false;
    return areRoleAssignmentsEqual(left.role_assignments, right.role_assignments);
  };

  const executeRerun = (prompt, config, sourceConfig) => {
    if (!prompt || !config) return;
    if (areConfigsEqual(config, sourceConfig)) {
      setRerunConfirm({ open: true, prompt, config });
      return;
    }
    onSendMessage(prompt, {
      modelPairingIdOverride: config.model_pairing_id || null,
      roleAssignmentsOverride: config.role_assignments || null,
      rerunContextOverride: {
        profile_id: config.profile_id || null,
        packet_id: config.packet_id || null,
        model_pairing_id: config.model_pairing_id || null,
      },
    });
  };

  const triggerRerun = (assistantMessageIndex, message) => {
    if (isLoading) return;
    const prompt = getPromptForAssistantMessage(assistantMessageIndex);
    if (!prompt) return;

    const metadata = message?.metadata || {};
    const runContext = metadata.run_context || {};
    const sourceConfig = normalizeConfig({
      profile_id: runContext.profile_id,
      packet_id: runContext.packet_id || '',
      model_pairing_id: runContext.model_pairing_id || selectedModelPairingId,
      role_assignments: roleAssignmentsListToMap(metadata.role_assignments || []),
      models: Object.keys(message?.stage1 || {}),
    });
    const currentConfig = normalizeConfig({
      profile_id: selectedProfileId,
      packet_id: selectedPacketId || '',
      model_pairing_id: selectedModelPairingId,
      role_assignments: currentRoleAssignments || {},
      models: selectedPairingModels || [],
    });

    const isContextDifferent =
      sourceConfig.profile_id !== currentConfig.profile_id ||
      sourceConfig.packet_id !== currentConfig.packet_id;

    if (isContextDifferent) {
      setRerunChoice({
        open: true,
        prompt,
        sourceConfig,
        currentConfig,
      });
      return;
    }

    executeRerun(prompt, currentConfig, sourceConfig);
  };

  if (!conversation) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-background">
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <h2 className="text-xl font-semibold text-foreground">Welcome to LLM Council</h2>
          <p className="mt-1 text-sm text-muted-foreground">Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-background">
      <Modal
        open={rerunConfirm.open}
        onClose={() => setRerunConfirm({ open: false, prompt: '', config: null })}
        title="Settings unchanged"
        description="You are about to re-run with the same profile, packet, model pairing, and role assignments."
        primaryAction="Re-run anyway"
        secondaryAction="Cancel"
        onPrimaryAction={() => {
          const prompt = rerunConfirm.prompt;
          const config = rerunConfirm.config;
          setRerunConfirm({ open: false, prompt: '', config: null });
          if (prompt && config) {
            onSendMessage(prompt, {
              modelPairingIdOverride: config.model_pairing_id || null,
              roleAssignmentsOverride: config.role_assignments || null,
              rerunContextOverride: {
                profile_id: config.profile_id || null,
                packet_id: config.packet_id || null,
                model_pairing_id: config.model_pairing_id || null,
              },
            });
          }
        }}
        onSecondaryAction={() => setRerunConfirm({ open: false, prompt: '', config: null })}
      >
        <p className="text-sm text-muted-foreground">
          This will likely produce similar output and consume additional tokens. Continue?
        </p>
      </Modal>

      <Modal
        open={rerunChoice.open}
        onClose={() => setRerunChoice({ open: false, prompt: '', sourceConfig: null, currentConfig: null })}
        title="Choose rerun profile context"
        description="Choose exactly which run config to use for this rerun."
        primaryAction="Use original context"
        secondaryAction="Use current sidebar context"
        onPrimaryAction={() => {
          const { prompt, sourceConfig } = rerunChoice;
          setRerunChoice({ open: false, prompt: '', sourceConfig: null, currentConfig: null });
          executeRerun(prompt, sourceConfig, sourceConfig);
        }}
        onSecondaryAction={() => {
          const { prompt, sourceConfig, currentConfig } = rerunChoice;
          setRerunChoice({ open: false, prompt: '', sourceConfig: null, currentConfig: null });
          executeRerun(prompt, currentConfig, sourceConfig);
        }}
      >
        <div className="space-y-2 text-sm text-muted-foreground">
          {renderConfigSummary('Original', rerunChoice.sourceConfig)}
          {renderConfigSummary('Current', rerunChoice.currentConfig, selectedModelPairingLabel)}
        </div>
      </Modal>

      <InterrogatorModal
        key={`${interrogationState?.sessionId || 'none'}-${interrogationState?.questionNumber || 0}`}
        isOpen={Boolean(interrogationState?.isOpen)}
        question={interrogationState?.question || ''}
        questionNumber={interrogationState?.questionNumber || 1}
        minQuestions={interrogationState?.minQuestions || 2}
        maxQuestions={interrogationState?.maxQuestions || 5}
        isSubmitting={Boolean(interrogationState?.isSubmitting)}
        onSubmitAnswer={onSubmitInterrogationAnswer}
        onDefer={onDeferInterrogation}
        onCancel={onCancelInterrogation}
      />

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {(selectedProfileId || selectedPacketId) && (
          <div className="mb-1 inline-flex rounded-full border border-border bg-muted px-3 py-1 text-xs text-muted-foreground">
            Active Guardrails: {selectedProfileId || 'default'}
            {selectedPacketId ? ` / packet: ${selectedPacketId}` : ''}
          </div>
        )}

        {conversation.messages.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-6 text-center">
            <h2 className="text-lg font-semibold text-foreground">Start a conversation</h2>
            <p className="mt-1 text-sm text-muted-foreground">Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="space-y-2">
              {msg.role === 'user' ? (
                <div className="ml-auto w-full max-w-3xl rounded-lg border border-primary/30 bg-primary/10 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary">You</div>
                  <div className="markdown-content text-sm text-foreground">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <div className="w-full max-w-5xl space-y-2 rounded-lg border border-border bg-card p-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    LLM Council
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {msg.metadata?.run_context?.profile_id && (
                      <div className="inline-flex w-fit rounded-full border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                        Profile: {msg.metadata.run_context.profile_id}
                        {msg.metadata.run_context.packet_id
                          ? ` | Packet: ${msg.metadata.run_context.packet_id}`
                          : ''}
                      </div>
                    )}
                    {msg.metadata?.guardrail_status?.status &&
                      msg.metadata.guardrail_status.status !== 'off' && (
                        <GuardrailStatusPill guardrailStatus={msg.metadata.guardrail_status} />
                      )}
                  </div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <div className="size-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <div className="size-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
                      <span>Running Stage 2: Peer rankings...</span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                    />
                  )}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <div className="size-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && (
                    <Stage3
                      finalResponse={msg.stage3}
                      onSaveVerdict={() => onSaveVerdictAsMarkdown(index)}
                      existingVerdict={msg.metadata?.verdict_markdown}
                      onRerun={() => triggerRerun(index, msg)}
                      rerunDisabled={isLoading}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
            <div className="size-4 animate-spin rounded-full border-2 border-border border-t-primary"></div>
            <span>Consulting the council...</span>
            <Button type="button" size="sm" variant="secondary" onClick={onStopCouncil}>
              Stop
            </Button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form className="border-t border-border bg-card p-4" onSubmit={handleSubmit}>
          <textarea
            className="min-h-28 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading || Boolean(interrogationState?.isOpen)}
            rows={3}
          />
          <Button
            type="submit"
            className="mt-3"
            disabled={!input.trim() || isLoading || Boolean(interrogationState?.isOpen)}
          >
            Send
          </Button>
        </form>
      )}
    </div>
  );
}
