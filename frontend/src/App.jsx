import { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import SettingsModal from './components/SettingsModal';
import { api } from './api';

const MODEL_PAIRING_STORAGE_KEY = 'llm-council:model-pairing-id';
const ROLE_ASSIGNMENTS_STORAGE_KEY = 'llm-council:role-assignments-by-pairing';
const PRIVACY_SAFE_MODELS_CACHE_STORAGE_KEY = 'llm-council:privacy-safe-models-cache';
const PRIVACY_SAFE_MODELS_CHECK_THROTTLE_MS = 2 * 60 * 1000;

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [interrogationState, setInterrogationState] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [packets, setPackets] = useState([]);
  const [selectedPacketId, setSelectedPacketId] = useState('');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [modelPairings, setModelPairings] = useState([]);
  const [pairingProfiles, setPairingProfiles] = useState({});
  const [selectedModelPairingId, setSelectedModelPairingId] = useState('premium');
  const [settingsProfileTabId, setSettingsProfileTabId] = useState('');
  const [roleAssignmentsByPairing, setRoleAssignmentsByPairing] = useState({});
  const [privacyModelOptionsState, setPrivacyModelOptionsState] = useState({
    isLoading: false,
    isCheckingUpdates: false,
    hasNewModels: false,
    lastRefreshedAt: 0,
    models: [],
    counts: null,
    error: '',
    catalogError: '',
  });
  const packetLoadRequestIdRef = useRef(0);
  const streamAbortControllerRef = useRef(null);
  const privacyModelCheckInFlightRef = useRef(false);
  const lastPrivacyModelCheckAtRef = useRef(0);

  async function loadConversations() {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  }

  async function loadConversation(id) {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  }

  async function loadProfilePackets(profileId) {
    const requestId = ++packetLoadRequestIdRef.current;
    try {
      const data = await api.listProfilePackets(profileId);
      if (requestId !== packetLoadRequestIdRef.current) return;
      const availablePackets = data.packets || [];
      setPackets(availablePackets);
      setSelectedPacketId((prev) => {
        if (prev && availablePackets.some((packet) => packet.packet_id === prev)) {
          return prev;
        }
        return availablePackets[0]?.packet_id || '';
      });
    } catch (error) {
      if (requestId !== packetLoadRequestIdRef.current) return;
      console.error('Failed to load profile packets:', error);
      setPackets([]);
      setSelectedPacketId('');
    }
  }

  const getPairingKey = (profileId, pairingId) =>
    `${profileId || 'none'}::${pairingId || 'premium'}`;

  const getSelectedPairing = () =>
    modelPairings.find((pairing) => pairing.id === selectedModelPairingId) || modelPairings[0] || null;

  const getAssignableModels = () => {
    const privacySafe = (privacyModelOptionsState.models || []).map((item) => item.id);
    if (privacySafe.length) return privacySafe;
    return [];
  };

  const savePrivacyModelCache = (nextState) => {
    const payload = {
      models: nextState.models || [],
      counts: nextState.counts || null,
      error: nextState.error || '',
      catalogError: nextState.catalogError || '',
      lastRefreshedAt: nextState.lastRefreshedAt || Date.now(),
    };
    localStorage.setItem(PRIVACY_SAFE_MODELS_CACHE_STORAGE_KEY, JSON.stringify(payload));
  };

  const applyPrivacySafeModelsPayload = (result) => {
    const nextState = {
      isLoading: false,
      isCheckingUpdates: false,
      hasNewModels: false,
      lastRefreshedAt: Date.now(),
      models: result.models || [],
      counts: result.counts || null,
      error: result.error || '',
      catalogError: result.catalog_error || '',
    };
    setPrivacyModelOptionsState((prev) => ({
      ...prev,
      ...nextState,
    }));
    savePrivacyModelCache(nextState);
  };

  const refreshPrivacySafeModels = async () => {
    setPrivacyModelOptionsState((prev) => ({
      ...prev,
      isLoading: true,
      error: '',
    }));
    try {
      const result = await api.getPrivacySafeModels();
      applyPrivacySafeModelsPayload(result);
    } catch (error) {
      setPrivacyModelOptionsState((prev) => ({
        ...prev,
        isLoading: false,
        error: error.message || 'Failed to load privacy-safe models',
      }));
    }
  };

  const checkForPrivacySafeModelUpdates = async () => {
    const now = Date.now();
    if (privacyModelCheckInFlightRef.current) return;
    if (now - lastPrivacyModelCheckAtRef.current < PRIVACY_SAFE_MODELS_CHECK_THROTTLE_MS) {
      return;
    }
    privacyModelCheckInFlightRef.current = true;
    lastPrivacyModelCheckAtRef.current = now;
    setPrivacyModelOptionsState((prev) => ({ ...prev, isCheckingUpdates: true }));
    try {
      const result = await api.getPrivacySafeModels();
      const nextIds = (result.models || []).map((item) => item.id).sort();
      setPrivacyModelOptionsState((prev) => {
        const currentIds = (prev.models || []).map((item) => item.id).sort();
        const hasNewModels =
          JSON.stringify(nextIds) !== JSON.stringify(currentIds) &&
          nextIds.length > 0;
        return {
          ...prev,
          isCheckingUpdates: false,
          hasNewModels: hasNewModels || prev.hasNewModels,
        };
      });
    } catch {
      setPrivacyModelOptionsState((prev) => ({
        ...prev,
        isCheckingUpdates: false,
      }));
    } finally {
      privacyModelCheckInFlightRef.current = false;
    }
  };

  const inferModelFeatures = (model, modelMeta = {}) => {
    const lower = (model || '').toLowerCase();
    const sizeMatches = [...lower.matchAll(/(\d+)(?:b|m)/g)];
    const sizeHints = sizeMatches.map((m) => Number.parseInt(m[1], 10)).filter(Number.isFinite);
    const maxSizeHint = sizeHints.length ? Math.max(...sizeHints) : 0;
    const contextLength = Number(modelMeta.context_length || 0);
    const tier = modelMeta.tier || 'paid';
    const supportsTools = Boolean(modelMeta.supports_tools);
    const fastHint = /(mini|nano|flash|lite|small)/.test(lower);
    const reasoningHint = /(reason|r1|o1|o3|sonnet|opus|qwen3|nemotron|deepseek|gpt-5|claude)/.test(lower);
    const codingHint = /(coder|code|dev)/.test(lower);
    return {
      tier,
      contextLength,
      supportsTools,
      fastHint,
      reasoningHint,
      codingHint,
      maxSizeHint,
      lower,
    };
  };

  const scoreModelForRole = (roleId, model, modelMeta = {}) => {
    const f = inferModelFeatures(model, modelMeta);
    let score = 0;

    if (f.tier === 'paid') score += 4;
    if (f.supportsTools) score += 1.5;
    if (f.contextLength >= 200000) score += 2.5;
    else if (f.contextLength >= 100000) score += 1.5;
    else if (f.contextLength >= 32000) score += 0.5;

    const roleWeights = {
      systems_thinker: { reasoning: 3.0, context: 2.0, large: 1.5, fast: -0.5 },
      conversion_operator: { reasoning: 1.0, context: 0.5, large: -0.5, fast: 2.0 },
      audience_psychologist: { reasoning: 2.0, context: 1.0, large: 0.5, fast: 0.5 },
      skeptic_auditor: { reasoning: 3.5, context: 1.5, large: 2.0, fast: -1.0 },
      pm_strategist: { reasoning: 2.5, context: 2.0, large: 1.0, fast: 0.0 },
      staff_engineer: { reasoning: 2.5, context: 1.0, large: 1.0, fast: -0.5, coding: 2.5 },
      adoption_analyst: { reasoning: 1.5, context: 1.5, large: 0.5, fast: 1.0 },
      failure_mode_reviewer: { reasoning: 3.5, context: 1.5, large: 1.5, fast: -1.0 },
      market_mapper: { reasoning: 2.5, context: 2.0, large: 1.0, fast: 0.0 },
      deal_operator: { reasoning: 1.5, context: 0.5, large: -0.5, fast: 2.0 },
      objection_strategist: { reasoning: 3.0, context: 1.0, large: 1.0, fast: 0.0 },
      commercial_risk_auditor: { reasoning: 3.5, context: 1.5, large: 1.5, fast: -1.0 },
    };
    const w = roleWeights[roleId] || {
      reasoning: 2.0,
      context: 1.0,
      large: 0.5,
      fast: 0.0,
      coding: 0.0,
    };

    if (f.reasoningHint) score += w.reasoning;
    if (f.fastHint) score += w.fast;
    if (f.maxSizeHint >= 70) score += w.large;
    if (f.contextLength >= 200000) score += w.context;
    if (f.codingHint) score += (w.coding || 0);

    return score;
  };

  const buildAutoAssignments = (profileId, pairingId, existing = {}) => {
    const roleCards = pairingProfiles[profileId]?.perspective_roles || [];
    const councilModels = getAssignableModels();
    if (!roleCards.length || !councilModels.length) {
      return existing;
    }

    const modelMetaMap = Object.fromEntries(
      (privacyModelOptionsState.models || []).map((item) => [item.id, item])
    );
    const next = { ...existing };
    const used = new Set(Object.values(next));

    roleCards.forEach((role) => {
      if (next[role.id] && councilModels.includes(next[role.id])) {
        return;
      }

      const ranked = [...councilModels].sort((a, b) => {
        const scoreA = scoreModelForRole(role.id, a, modelMetaMap[a]);
        const scoreB = scoreModelForRole(role.id, b, modelMetaMap[b]);
        if (scoreA !== scoreB) return scoreB - scoreA;
        return a.localeCompare(b);
      });
      const uniquePreferred = ranked.find((model) => !used.has(model));
      const selected = uniquePreferred || ranked[0];
      next[role.id] = selected;
      used.add(selected);
    });

    return next;
  };

  const getCurrentRoleAssignmentOverride = (profileId = selectedProfileId) => {
    const key = getPairingKey(profileId, selectedModelPairingId);
    const existing = roleAssignmentsByPairing[key] || {};
    return buildAutoAssignments(profileId, selectedModelPairingId, existing);
  };

  // Load conversations on mount
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadConversations();

    const loadInitialProfiles = async () => {
      try {
        const data = await api.listProfiles();
        const availableProfiles = data.profiles || [];
        setProfiles(availableProfiles);
        if (!availableProfiles.length) return;

        const resolvedProfileId = data.default_profile_id || availableProfiles[0].id;
        setSelectedProfileId(resolvedProfileId);
        setSettingsProfileTabId(resolvedProfileId);
        await loadProfilePackets(resolvedProfileId);
      } catch (error) {
        console.error('Failed to load profiles:', error);
      }
    };

    const loadModelSettings = async () => {
      try {
        const settings = await api.listModelPairings();
        setModelPairings(settings.pairings || []);
        setPairingProfiles(settings.profiles || {});

        const storedPairing = localStorage.getItem(MODEL_PAIRING_STORAGE_KEY);
        const defaultPairing = settings.default_model_pairing_id || 'premium';
        const knownPairings = new Set((settings.pairings || []).map((p) => p.id));
        const resolvedPairingId =
          storedPairing && knownPairings.has(storedPairing)
            ? storedPairing
            : defaultPairing;
        setSelectedModelPairingId(resolvedPairingId);

        const savedOverridesRaw = localStorage.getItem(
          ROLE_ASSIGNMENTS_STORAGE_KEY
        );
        if (savedOverridesRaw) {
          setRoleAssignmentsByPairing(JSON.parse(savedOverridesRaw));
        }

        const cachedPrivacyModelsRaw = localStorage.getItem(
          PRIVACY_SAFE_MODELS_CACHE_STORAGE_KEY
        );
        if (cachedPrivacyModelsRaw) {
          const cached = JSON.parse(cachedPrivacyModelsRaw);
          setPrivacyModelOptionsState((prev) => ({
            ...prev,
            isLoading: false,
            isCheckingUpdates: false,
            hasNewModels: false,
            lastRefreshedAt: Number(cached.lastRefreshedAt || 0),
            models: cached.models || [],
            counts: cached.counts || null,
            error: cached.error || '',
            catalogError: cached.catalogError || '',
          }));
        }
      } catch (error) {
        console.error('Failed to load model settings:', error);
      }
    };

    loadInitialProfiles();
    loadModelSettings();
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  useEffect(() => {
    if (!isSettingsOpen) return;
    checkForPrivacySafeModelUpdates();
  }, [isSettingsOpen]);

  useEffect(() => {
    if (!profiles.length) return;
    if (!settingsProfileTabId || !profiles.some((p) => p.id === settingsProfileTabId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSettingsProfileTabId(selectedProfileId || profiles[0].id);
    }
  }, [profiles, selectedProfileId, settingsProfileTabId]);

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, message_count: 0 },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setInterrogationState(null);
    setCurrentConversationId(id);
  };

  const handleSelectProfile = async (profileId) => {
    setSelectedProfileId(profileId);
    await loadProfilePackets(profileId);
  };

  const handleSelectModelPairing = (pairingId) => {
    setSelectedModelPairingId(pairingId);
    localStorage.setItem(MODEL_PAIRING_STORAGE_KEY, pairingId);
  };

  const handleChangeRoleAssignment = (profileId, roleId, model) => {
    const key = getPairingKey(profileId, selectedModelPairingId);
    setRoleAssignmentsByPairing((prev) => {
      const next = {
        ...prev,
        [key]: {
          ...(prev[key] || {}),
          [roleId]: model,
        },
      };
      localStorage.setItem(ROLE_ASSIGNMENTS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const handleApplySmartDefaults = (profileId) => {
    const key = getPairingKey(profileId, selectedModelPairingId);
    const smart = buildAutoAssignments(profileId, selectedModelPairingId, {});
    setRoleAssignmentsByPairing((prev) => {
      const next = {
        ...prev,
        [key]: smart,
      };
      localStorage.setItem(ROLE_ASSIGNMENTS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const handleDeleteConversation = async (id) => {
    try {
      await api.deleteConversation(id);
      const nextConversations = conversations.filter((conv) => conv.id !== id);
      setConversations(nextConversations);

      if (currentConversationId === id) {
        setInterrogationState(null);
        setCurrentConversationId(nextConversations[0]?.id || null);
        if (nextConversations.length === 0) {
          setCurrentConversation(null);
        }
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleSaveVerdictAsMarkdown = async (assistantMessageIndex) => {
    if (!currentConversationId) return null;

    try {
      return await api.saveVerdictAsMarkdown(
        currentConversationId,
        assistantMessageIndex
      );
    } catch (error) {
      console.error('Failed to save verdict markdown:', error);
      throw error;
    }
  };

  const runCouncilMessage = async (content, interrogation = null, options = {}) => {
    if (!currentConversationId) return;
    const {
      modelPairingIdOverride = selectedModelPairingId,
      roleAssignmentsOverride = getCurrentRoleAssignmentOverride(),
      rerunContextOverride = null,
    } = options;

    setIsLoading(true);
    try {
      const abortController = new AbortController();
      streamAbortControllerRef.current = abortController;

      // Optimistically add user message to UI
      const userMessage = { role: 'user', content };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: {
          stage1: false,
          stage2: false,
          stage3: false,
        },
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      await api.sendMessageStream(
        currentConversationId,
        content,
        (eventType, event) => {
          switch (eventType) {
            case 'stage1_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.loading.stage1 = true;
                return { ...prev, messages };
              });
              break;

            case 'stage1_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.stage1 = event.data;
                lastMsg.loading.stage1 = false;
                return { ...prev, messages };
              });
              break;

            case 'stage2_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.loading.stage2 = true;
                return { ...prev, messages };
              });
              break;

            case 'stage2_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.stage2 = event.data;
                lastMsg.metadata = event.metadata;
                lastMsg.loading.stage2 = false;
                return { ...prev, messages };
              });
              break;

            case 'stage3_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.loading.stage3 = true;
                return { ...prev, messages };
              });
              break;

            case 'stage3_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const lastMsg = messages[messages.length - 1];
                lastMsg.stage3 = event.data;
                lastMsg.loading.stage3 = false;
                return { ...prev, messages };
              });
              break;

            case 'title_complete':
              // Reload conversations to get updated title
              loadConversations();
              break;

            case 'complete':
              // Stream complete, reload conversations list
              loadConversations();
              setIsLoading(false);
              break;

            case 'error':
              console.error('Stream error:', event.message);
              setIsLoading(false);
              break;

            default:
              console.log('Unknown event type:', eventType);
          }
        },
        interrogation,
        modelPairingIdOverride,
        roleAssignmentsOverride,
        null,
        rerunContextOverride,
        abortController.signal
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      if (error?.name === 'AbortError') {
        // Keep the user prompt visible and remove only the unfinished assistant placeholder.
        setCurrentConversation((prev) => {
          const messages = [...(prev?.messages || [])];
          const last = messages[messages.length - 1];
          if (last?.role === 'assistant' && !last.stage1 && !last.stage2 && !last.stage3) {
            messages.pop();
          }
          return { ...prev, messages };
        });
      } else {
        // Remove optimistic messages on network/server failure
        setCurrentConversation((prev) => ({
          ...prev,
          messages: prev.messages.slice(0, -2),
        }));
      }
      setIsLoading(false);
    } finally {
      streamAbortControllerRef.current = null;
    }
  };

  const startInterrogation = async (content) => {
    if (!currentConversationId) return;

    try {
      const started = await api.startInterrogation(
        currentConversationId,
        content,
        selectedProfileId,
        selectedPacketId,
        selectedModelPairingId
      );
      setInterrogationState({
        isOpen: true,
        isSubmitting: false,
        sessionId: started.session_id,
        originalContent: content,
        profileId: started.profile_id,
        packetId: started.packet_id,
        question: started.question,
        questionNumber: started.question_number,
        minQuestions: started.min_questions,
        maxQuestions: started.max_questions,
      });
    } catch (error) {
      console.error('Failed to start interrogation:', error);
    }
  };

  const handleSubmitInterrogationAnswer = async (answer) => {
    if (!interrogationState?.isOpen || !currentConversationId) return;

    setInterrogationState((prev) => ({ ...prev, isSubmitting: true }));
    try {
      const response = await api.submitInterrogationAnswer(
        currentConversationId,
        interrogationState.sessionId,
        answer
      );

      if (!response.done) {
        setInterrogationState((prev) => ({
          ...prev,
          isSubmitting: false,
          question: response.question,
          questionNumber: response.question_number,
        }));
        return;
      }

      const originalContent = interrogationState.originalContent;
      const interrogationPayload = response.interrogation;
      setInterrogationState(null);
      await runCouncilMessage(originalContent, interrogationPayload);
    } catch (error) {
      console.error('Failed during interrogation:', error);
      setInterrogationState((prev) =>
        prev ? { ...prev, isSubmitting: false } : prev
      );
    }
  };

  const handleDeferInterrogation = async () => {
    await handleSubmitInterrogationAnswer('__DEFER_TO_COUNCIL__');
  };

  const handleCancelInterrogation = () => {
    setInterrogationState(null);
  };

  const handleSendMessage = async (content, options = null) => {
    if (!currentConversationId) return;
    const isFirstMessage = (currentConversation?.messages?.length ?? 0) === 0;

    if (isFirstMessage) {
      await startInterrogation(content);
      return;
    }

    await runCouncilMessage(content, null, options || {});
  };

  const handleStopCouncil = () => {
    streamAbortControllerRef.current?.abort();
  };

  const selectedPairing = getSelectedPairing();
  const selectedPairingLabel = selectedPairing?.label || '';
  const activeSettingsProfileId = settingsProfileTabId || selectedProfileId;
  const roleCardsByProfile = Object.fromEntries(
    Object.entries(pairingProfiles).map(([profileId, profile]) => [
      profileId,
      profile?.perspective_roles || [],
    ])
  );
  const roleAssignmentsByProfile = Object.fromEntries(
    Object.keys(roleCardsByProfile).map((profileId) => [
      profileId,
      getCurrentRoleAssignmentOverride(profileId),
    ])
  );
  const currentRoleAssignments = roleAssignmentsByProfile[activeSettingsProfileId] || {};
  const selectedProfileRoleAssignments = roleAssignmentsByProfile[selectedProfileId] || {};
  const duplicateRoleWarning = (() => {
    const reverse = {};
    Object.entries(currentRoleAssignments).forEach(([roleId, model]) => {
      if (!model) return;
      reverse[model] = reverse[model] || [];
      reverse[model].push(roleId);
    });
    const duplicates = Object.entries(reverse).filter(([, roles]) => roles.length > 1);
    if (!duplicates.length) {
      return '';
    }
    return duplicates
      .map(([model, roles]) => `${model} -> ${roles.join(', ')}`)
      .join(' | ');
  })();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        onSelectProfile={handleSelectProfile}
        packets={packets}
        selectedPacketId={selectedPacketId}
        onSelectPacket={setSelectedPacketId}
        selectedModelPairingLabel={selectedPairingLabel}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        pairings={modelPairings}
        selectedPairingId={selectedModelPairingId}
        onSelectPairing={handleSelectModelPairing}
        profiles={profiles}
        activeProfileId={activeSettingsProfileId}
        onSelectProfileTab={setSettingsProfileTabId}
        roleCardsByProfile={roleCardsByProfile}
        roleAssignmentsByProfile={roleAssignmentsByProfile}
        duplicateRoleWarning={duplicateRoleWarning}
        onChangeRoleAssignment={handleChangeRoleAssignment}
        onApplySmartDefaults={handleApplySmartDefaults}
        modelOptionsState={privacyModelOptionsState}
        onRefreshModels={refreshPrivacySafeModels}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        onStopCouncil={handleStopCouncil}
        isLoading={isLoading}
        onSaveVerdictAsMarkdown={handleSaveVerdictAsMarkdown}
        interrogationState={interrogationState}
        onSubmitInterrogationAnswer={handleSubmitInterrogationAnswer}
        onDeferInterrogation={handleDeferInterrogation}
        onCancelInterrogation={handleCancelInterrogation}
        selectedProfileId={selectedProfileId}
        selectedPacketId={selectedPacketId}
        selectedModelPairingId={selectedModelPairingId}
        selectedModelPairingLabel={selectedPairingLabel}
        selectedPairingModels={selectedPairing?.council_models || []}
        modelPairings={modelPairings}
        currentRoleAssignments={selectedProfileRoleAssignments}
      />
    </div>
  );
}

export default App;
